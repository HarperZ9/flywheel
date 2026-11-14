"""gateway_ledger_gate.py -- no ledger, no model call.

The gateway records every model call in its ledger (gateway_ledger). When the
ledger cannot be opened, the call must not reach a provider: a reply that
cannot be recorded would be billed with nothing to show for it. The ledger is
unavailable when

  - another gateway process on the same Flywheel home holds the writer lock,
  - any other process holds the writer lock,
  - the ledger folder cannot be created or written, or
  - a write failed after the ledger had opened (a full disk, for one) and the
    ledger has not resumed (gateway_ledger_health).

Each model interface asks here before it contacts an upstream:

  refusal(path)        the 503 for /v1/messages, /v1/messages/count_tokens and
                       /v1/responses, in that interface's error shape
  required(ledger_of)  the ledger for the chat paths (/v1/chat/completions,
                       /api/route), or LedgerUnavailable
  typed_refusal(exc)   the 503 body for LedgerUnavailable; any other exception
                       goes to model_selection_response as before
  startup(ledger_of)   one line at gateway start that says whether the ledger
                       opened

The answer is 503 with `retry-after`: the state ends when the other process
stops or the folder becomes writable, and the gateway tries the ledger again
on every call. Nothing here reads a key or a request body.
"""
from __future__ import annotations

import logging
import uuid

from .model_selection_required import model_selection_response

_LOG = logging.getLogger(__name__)
RETRY_AFTER = "5"
CODE = "ledger_unavailable"
TEXT = ("the gateway ledger cannot be opened or written, so the call was refused and "
        "nothing was sent upstream. Another gateway may be running on this Flywheel home, "
        "or the gateway-ledger folder is not writable. The gateway log names the cause")


class LedgerUnavailable(Exception):
    """The gateway has no ledger to record a model call in."""

    status = 503


def refusal(path: str):
    """The 503 `Response` for a model interface path."""
    from .gateway_turn import Response
    _LOG.error("gateway request on %s refused with 503: the ledger is unavailable", path)
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    if path == "/v1/responses":
        from .gateway_responses_reply import error
        return Response(503, error(503, TEXT, None, CODE),
                        headers={"x-request-id": request_id, "retry-after": RETRY_AFTER})
    from .gateway_messages_wire import error
    return Response(503, error(503, TEXT, request_id),
                    headers={"request-id": request_id, "retry-after": RETRY_AFTER})


def required(ledger_of):
    """The ledger `ledger_of()` returns, or LedgerUnavailable when it is None."""
    ledger = ledger_of()
    if ledger is None:
        _LOG.error("gateway chat call refused with 503: the ledger is unavailable")
        raise LedgerUnavailable(TEXT)
    return ledger


def typed_refusal(exc: Exception) -> "tuple[dict, int] | None":
    """(body, status) for an exception that has its own answer, else None."""
    if isinstance(exc, LedgerUnavailable):
        return {"error": {"message": str(exc), "type": "server_error", "param": None,
                          "code": CODE}}, exc.status
    return model_selection_response(exc)


def startup(ledger_of, out=print) -> bool:
    """Open the ledger once at gateway start and say plainly what happened."""
    ledger = ledger_of()
    if ledger is None:
        out("  LEDGER    UNAVAILABLE: the gateway ledger cannot be opened or written. Model "
            "calls answer 503 and reach no provider until it can. Is another gateway running "
            "on this Flywheel home? The cause is in the log line above.")
        return False
    where = getattr(ledger, "path", None)
    broken = getattr(ledger, "found_broken", None)
    out(f"  ledger    {where or 'in memory'}  ({len(ledger.entries)} entries in this segment"
        + (f"; BROKEN before it: {broken}; run `flywheel gateway-ledger verify`)" if broken
           else ")"))
    if where is not None:
        from .gateway_ledger_health import strays
        for name in strays(where.parent):
            out(f"  ledger    ignored {name!r}: its name is not a segment's, so it is not "
                "part of the ledger")
    return True
