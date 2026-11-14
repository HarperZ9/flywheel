"""gateway_unaccounted.py -- a call the upstream answered that could not be accounted.

`gateway_turn.record` debits the caller and appends the ledger entry after the
upstream has answered. When either step fails, the call still happened and the
provider still bills it, so the record must say so. `unaccounted` writes that
entry, suspends the key when the reply's text had already left, and returns
the error the client is told. `provider_tools` reads what the provider says
its own tools did, for the served entry.
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
