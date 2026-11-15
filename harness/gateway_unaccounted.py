"""gateway_unaccounted.py -- a call the upstream answered that could not be accounted.

`gateway_turn.record` debits the caller and appends the ledger entry after the
upstream has answered. When either step fails, the call still happened and the
provider still bills it, so the record must say so. `unaccounted` writes that
entry, suspends the key when the reply's text had already left, and returns
the error the client is told. `provider_tools` reads what the provider says
its own tools did, for the served entry. `partial_charge` charges a key for a
stream that began and did not finish.
"""
from __future__ import annotations

import json
import logging

from .gateway_turn import _APPEND, AccountingFailed, call_meta, prompt_sha

_LOG = logging.getLogger(__name__)


def provider_tools(reply) -> dict:
    """What the provider says its own tools did (`usage.server_tool_use`), if anything."""
    usage = reply.raw.get("usage") if isinstance(reply.raw, dict) else None
    used = usage.get("server_tool_use") if isinstance(usage, dict) else None
    counts = {k: v for k, v in used.items() if type(v) is int} if isinstance(used, dict) else {}
    return {"server_tool_use": counts} if counts else {}


def unaccounted(ledger, upstream, turn, bill, sha, cause, delivered,
                exc) -> AccountingFailed:
    """The upstream answered and the debit or the append failed.

    The ledger gets `endpoint_call_failed` with the response hash: reason
    `charge_failed` or `ledger_failed` for a reply that was held back, and
    `delivered_unrecorded_charge` for a stream whose text already left. In
    that case the key is suspended until an operator clears it. Returns the
    error the client is told."""
    from .provider_fault_boundary import redacted_text
    reason = "delivered_unrecorded_charge" if delivered else cause
    who = bill.caller.name
    _LOG.error("gateway %s call to %s for %s answered but %s (%s: %s); delivered=%s",
               turn.interface, upstream.name, who, cause, type(exc).__name__,
               redacted_text(str(exc)), delivered)
    meta = {"endpoint": upstream.name, "interface": turn.interface,
            "prompt_sha": prompt_sha(turn), "response_sha": sha, "reason": reason,
            "cause": cause, "delivered": bool(delivered), **bill.meta, **call_meta(turn)}
    try:
        with _APPEND:
            ledger.append("endpoint_call_failed", reason, meta)
    except Exception as again:  # noqa: BLE001 - kept for the resume; the client is told
        from .gateway_calls import defer
        defer(ledger, "endpoint_call_failed", reason, meta)
        _LOG.error("gateway ledger refused the accounting-failure entry as well (%s: %s)",
                   type(again).__name__, redacted_text(str(again)))
    what = ("could not be charged to its gateway key" if cause == "charge_failed"
            else "could not be recorded in the gateway ledger")
    if not delivered:
        return AccountingFailed(f"the upstream answered, but the call {what}; the reply "
                                f"was not served ({cause})", status=500, reason=reason)
    held = bill.suspend(reason)
    return AccountingFailed(
        f"the text already sent on this stream was delivered, but the call {what} "
        f"(delivered_unrecorded_charge){held}", status=500, reason=reason)


def _beside_text(assembler) -> str:
    """What a stream carried besides its text: tool-call arguments and thinking.

    Read from whichever assembler the upstream's format uses. A provider
    bills these as output, so an unfinished stream is charged for them too."""
    parts = []
    for block in (getattr(assembler, "blocks", None) or {}).values():       # Anthropic
        parts.append(block.get("thinking"))
        if block.get("input"):
            parts.append(json.dumps(block["input"]))
    held = getattr(assembler, "partial", None)                  # arguments still arriving
    parts.extend(held.values() if isinstance(held, dict) else [])
    for call in (getattr(assembler, "calls", None) or {}).values():         # OpenAI format
        parts.append((call.get("function") or {}).get("arguments"))
    extra = getattr(assembler, "extra", None)                   # reasoning text
    parts.extend(extra.values() if isinstance(extra, dict) else [])
    for part in getattr(assembler, "parts", None) or []:                    # Gemini
        if isinstance(part, dict):
            if part.get("thought") is True:
                parts.append(part.get("text"))
            if isinstance(part.get("functionCall"), dict):
                parts.append(json.dumps(part["functionCall"].get("args") or {}))
    return " ".join(part for part in parts if isinstance(part, str) and part)


def _reported(assembler) -> dict:
    """The counts the provider had sent before the stream stopped, under our names."""
    message = getattr(assembler, "message", None)
    found = message.get("usage") if isinstance(message, dict) else None     # Anthropic
    names = {"input": "input_tokens", "output": "output_tokens",
             "cache_read": "cache_read_input_tokens",
             "cache_write": "cache_creation_input_tokens"}
    if not isinstance(found, dict):
        found = getattr(assembler, "usage", None)                           # OpenAI format
        names = {"input": "prompt_tokens", "output": "completion_tokens"}
    if not isinstance(found, dict):
        found = (getattr(assembler, "last", None) or {}).get("usageMetadata")   # Gemini
        names = {"input": "promptTokenCount", "output": "candidatesTokenCount"}
    if not isinstance(found, dict):
        return {}
    return {ours: found[theirs] for ours, theirs in names.items()
            if type(found.get(theirs)) is int}


def partial_charge(turn, reason: str, assembler, pieces) -> dict:
    """Charge a key for a stream that did not finish; returns the entry's extra meta.

    A stream the client closed, or one the upstream cut after it began, has
    cost the provider account something. The key pays

      input   the count the provider had reported when the stream stopped
              (Anthropic's `message_start`, the usage chunk of an OpenAI-format
              stream, Gemini's `usageMetadata`), else the estimate of the
              prompt;
      output  the larger of the provider's reported output count, when one had
              arrived (Anthropic's `message_delta`), and the estimate of
              everything received: text, tool-call arguments and thinking.

    An estimate is the larger of the word count and a quarter of the
    characters, rounded up; the input estimate is also at least a quarter of
    the request's bytes, which counts tool definitions. An OpenAI-format
    stream reports usage in its last chunk, so every such stream that stops
    early is estimated, hosted OpenAI included. The entry is marked
    `estimated`. A stream the upstream cut before any event is not charged."""
    caller = turn.caller
    if caller is None or caller.row is None:
        return {}
    if reason != "client_disconnected" and not assembler.began:
        return {}
    from . import token_usage
    system, prompt = turn.text_form()
    sent = f"{system}\n{prompt}"
    received = " ".join(filter(None, ["".join(p for p in pieces if p), _beside_text(assembler)]))
    words = token_usage.estimate(sent, received)
    # A word count is near zero for text with no spaces (CJK, base64, minified
    # code), so each side is at least a quarter of its characters, rounded up:
    # the rule the reservation uses for a request's bytes. The text form leaves
    # out tool definitions, images and documents, so the input is also at least
    # the input this call reserved: a quarter of the whole request's bytes
    # (gateway_key_policy.admit), still held while the stream is closed.
    held = getattr(caller, "ticket", None)
    counts = {"input": max(words["prompt_words"], -(-len(sent) // 4), held[0] if held else 0),
              "output": max(words["completion_words"], -(-len(received) // 4))}
    reported = _reported(assembler)
    if "input" in reported:
        counts.update(input=reported["input"], cache_read=reported.get("cache_read", 0),
                      cache_write=reported.get("cache_write", 0))
    counts["output"] = max(counts["output"], reported.get("output", 0))
    try:
        caller.keys.debit(caller.name, counts, True)
    except Exception as exc:  # noqa: BLE001 - the entry below says the charge is missing
        _LOG.error("gateway key %s could not be charged for an unfinished stream (%s: %s)",
                   caller.name, type(exc).__name__, exc)
        return {"charged_tokens": 0, "estimated": True, "charge_failed": True}
    return {"charged_tokens": sum(counts.values()), "estimated": True}
