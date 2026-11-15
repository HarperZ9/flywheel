"""gateway_account.py -- the accounting guard at the point of upstream contact.

A model interface (gateway_messages, gateway_responses) reaches a provider
only through an `Account`. The rule it keeps: a call that contacted an
upstream leaves exactly one ledger entry, and a virtual key is charged for it
or stopped. Before this module a failure between the provider's answer and
the entry (a prompt that could not be hashed, for one) left a streamed reply
delivered with no entry and no charge.

  Account(ledger, upstream, turn)
      Made before the upstream is contacted. Everything an entry needs that
      does not depend on the reply is computed here: the flattened prompt,
      its hash and the caller's fields. If any of it cannot be computed the
      request is refused (`TurnRefused`, answered 400) and nothing is sent.
  account.reach(send)
      Calls `send`, the function that contacts the upstream. gateway_turn_call
      contacts an upstream nowhere else. `contacting()` names the account in
      use on this thread, so a test can see a contact made outside one.
  account.served(reply) / account.failed(reason, ...)
      The two ordinary ends: `endpoint_call` (gateway_turn.record) or
      `endpoint_call_failed` (gateway_turn.record_failed).
  account.lost(exc, delivered)
      The end for a fault nobody planned for, after contact. It appends
      `endpoint_call_failed` built only from the fields computed before
      contact, with reason `accounting_error`, or `delivered_unrecorded_charge`
      when a stream's text had already left, and it suspends a virtual key
      until an operator clears it: the cause is unknown, so the key holder
      could repeat it.
  account.settle(delivered)
      The backstop: a contacted account that reached none of the three ends
      is closed with `lost`.

`unbilled(send)` marks the one contact that is made with no account on
purpose: token counting, which the provider does not bill and the ledger
does not record (docs/KNOWN-LIMITS-2.0.0.md).

`encodable(value)` and `unencodable(path)` are the intake check: a request
body with a string that is not valid Unicode (a lone surrogate, sent as the
JSON escape \\ud800) is answered 400 before a key is admitted.

What this does not do. The entry is written after the provider answers,
because it holds the hash of the reply. A gateway that stops between the two
leaves no entry (docs/KNOWN-LIMITS-2.0.0.md).
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from . import gateway_turn as _turn

_LOG = logging.getLogger(__name__)
_CONTACT = contextvars.ContextVar("flywheel_gateway_contact", default=None)
UNBILLED = "unbilled"                   # what `contacting()` returns inside `unbilled`
REASON = "accounting_error"
TEXT = ("the request holds text that is not valid UTF-8 (a lone surrogate escape such as "
        "\\ud800), so the call cannot be hashed for the gateway ledger. Nothing was sent "
        "upstream")


def contacting():
    """The `Account` contacting an upstream on this thread, `UNBILLED`, or None."""
    return _CONTACT.get()


def encodable(value) -> bool:
    """True when every string in a parsed JSON value encodes as UTF-8."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if not item.isascii():
                try:
                    item.encode("utf-8")
                except UnicodeEncodeError:
                    return False
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return True


def unencodable(path: str):
    """The 400 `Response` for a body `encodable` refused, in the interface's error shape."""
    _LOG.info("gateway request on %s refused: its text is not valid UTF-8", path)
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    if path == "/v1/responses":
        from .gateway_responses_reply import error
        return _turn.Response(400, error(400, TEXT + "."), headers={"x-request-id": request_id})
    from .gateway_messages_wire import error
    return _turn.Response(400, error(400, TEXT + ".", request_id),
                          headers={"request-id": request_id})


def readable(backend, reply):
    """`reply`, or MalformedBackendOutput when its text cannot be hashed.

    The ledger entry and the receipt hash the reply's text. A reply that holds
    a lone surrogate is refused as malformed and recorded as a failed call."""
    if encodable([_turn.reply_text(reply), reply.model_ref, reply.served_model]):
        return reply
    from .local_agent import MalformedBackendOutput
    raise MalformedBackendOutput(
        f"{backend.name} reply holds text that is not valid UTF-8 (a lone surrogate); "
        "the reply was refused")


def unbilled(send):
    """Contact an upstream for a request that is not billed and not recorded."""
    token = _CONTACT.set(UNBILLED)
    try:
        return send()
    finally:
        _CONTACT.reset(token)


class Account:
    """The accounting of one upstream call. States: open, contacted, closed."""

    def __init__(self, ledger, upstream, turn):
        from .gateway_key_gate import OWNER
        if ledger is None:
            raise RuntimeError("the gateway ledger is unavailable; nothing was sent upstream")
        self.ledger, self.upstream, self.turn = ledger, upstream, turn
        self.caller, self.state = getattr(turn, "caller", None) or OWNER, "open"
        try:
            turn.text_form()            # kept on the turn: nothing later flattens it again
            self.base = {"endpoint": upstream.name, "interface": turn.interface,
                         "prompt_sha": _turn.prompt_sha(turn), **self.caller.meta}
            if not encodable(self.base):
                raise UnicodeError("a ledger field is not valid UTF-8")
        except UnicodeError as exc:
            raise _turn.TurnRefused("invalid", TEXT) from exc

    def reach(self, send):
        """Contact the upstream: call `send` and return what it returns."""
        if self.state == "closed":
            raise RuntimeError("this call is already recorded; it cannot contact an upstream")
        self.state = "contacted"
        token = _CONTACT.set(self)
        try:
            return send()
        finally:
            _CONTACT.reset(token)

    def served(self, reply, delivered: bool = False) -> None:
        """The upstream answered: debit the caller and append `endpoint_call`."""
        try:
            if delivered:
                _turn.record(self.ledger, self.upstream, self.turn, reply, delivered=True)
            else:
                _turn.record(self.ledger, self.upstream, self.turn, reply)
        except _turn.AccountingFailed:
            self.state = "closed"       # gateway_unaccounted wrote the entry
            raise
        except Exception as exc:        # noqa: BLE001 - whatever it was, the call is recorded
            raise self.lost(exc, delivered) from exc
        self.state = "closed"

    def failed(self, reason: str, detail="", partial=None) -> None:
        """The call did not produce a reply: append `endpoint_call_failed`."""
        try:
            _turn.record_failed(self.ledger, self.upstream, self.turn, reason, detail,
                                partial=partial)
        except Exception as exc:        # noqa: BLE001 - a partial charge may have been made
            raise self.lost(exc, partial is not None, charged=None) from exc
        self.state = "closed"

    def lost(self, exc: BaseException, delivered: bool, charged=0) -> "_turn.AccountingFailed":
        """Record a call whose accounting met a fault no one planned for.

        Uses only what was computed before contact. `charged` is what the key
        had been debited for the call when the fault came: 0 on the served
        path, where the debit is the last step before the entry, and None
        (left out of the entry) when it is not known. Returns the error the
        client is told."""
        from .provider_fault_boundary import redacted_text
        self.state = "closed"
        reason = "delivered_unrecorded_charge" if delivered else REASON
        _LOG.error("gateway %s call to %s for %s reached the provider and its accounting "
                   "failed (%s: %s); delivered=%s", self.turn.interface, self.upstream.name,
                   self.caller.name, type(exc).__name__, redacted_text(str(exc)), delivered)
        meta = {**self.base, "reason": reason, "cause": REASON,
                "error": type(exc).__name__, "delivered": bool(delivered)}
        held = ""
        if self.caller.row is not None:
            from .gateway_key_policy import suspend
            if charged is not None:
                meta["charged_tokens"] = charged
            held = suspend(self.caller, reason)
        try:
            with _turn._APPEND:
                self.ledger.append("endpoint_call_failed", reason, meta)
        except Exception as again:      # noqa: BLE001 - logged; the client is still told
            _LOG.error("gateway ledger refused the accounting-failure entry as well (%s: %s)",
                       type(again).__name__, redacted_text(str(again)))
        what = ("the text already sent on this stream was delivered" if delivered
                else "the reply was not served")
        return _turn.AccountingFailed(
            f"the upstream was called, but the call could not be accounted "
            f"({type(exc).__name__}); {what} ({reason}){held}", status=500, reason=reason)

    def settle(self, delivered: bool) -> None:
        """Close an account that contacted an upstream and was never recorded."""
        if self.state == "contacted":
            self.lost(RuntimeError("the call ended without a ledger entry"), delivered, None)
