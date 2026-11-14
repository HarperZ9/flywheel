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

import logging

from .gateway_turn import _APPEND, AccountingFailed, prompt_sha

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
            "cause": cause, "delivered": bool(delivered), **bill.meta}
    try:
        with _APPEND:
            ledger.append("endpoint_call_failed", reason, meta)
    except Exception as again:  # noqa: BLE001 - logged; the client is still told below
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


def partial_charge(turn, reason: str, assembler, pieces) -> dict:
    """Charge a key for a stream that did not finish; returns the entry's extra meta.

    A stream the client closed, or one the upstream cut after it began, has
    cost the provider account something. The key pays the input the provider
    reported at the start of the stream when it did (Anthropic's
    `message_start`), else the word estimate of the prompt, plus the word
    estimate of the text that was received. The entry is marked `estimated`.
    A stream the upstream cut before any event is not charged."""
    caller = turn.caller
    if caller is None or caller.row is None:
        return {}
    if reason != "client_disconnected" and not assembler.began:
        return {}
    from . import token_usage
    system, prompt = turn.text_form()
    words = token_usage.estimate(f"{system}\n{prompt}", "".join(p for p in pieces if p))
    counts = {"input": words["prompt_words"], "output": words["completion_words"]}
    message = getattr(assembler, "message", None)
    usage = message.get("usage") if isinstance(message, dict) else None
    if isinstance(usage, dict) and type(usage.get("input_tokens")) is int:
        counts["input"] = usage["input_tokens"]
        for ours, theirs in (("cache_read", "cache_read_input_tokens"),
                             ("cache_write", "cache_creation_input_tokens")):
            counts[ours] = usage[theirs] if type(usage.get(theirs)) is int else 0
    try:
        caller.keys.debit(caller.name, counts, True)
    except Exception as exc:  # noqa: BLE001 - the entry below says the charge is missing
        _LOG.error("gateway key %s could not be charged for an unfinished stream (%s: %s)",
                   caller.name, type(exc).__name__, exc)
        return {"charged_tokens": 0, "estimated": True, "charge_failed": True}
    return {"charged_tokens": sum(counts.values()), "estimated": True}
