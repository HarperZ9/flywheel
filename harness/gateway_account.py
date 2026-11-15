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

`unbilled(send, url)` marks the one contact that is made with no account on
purpose: token counting, which the provider does not bill and the ledger
does not record (docs/KNOWN-LIMITS-2.0.0.md). It refuses any URL that is not
a token-count URL, so the exception cannot carry another request.

`encodable(value)` and `unencodable(path)` are the intake check: a request
body with a string that is not valid Unicode (a lone surrogate, sent as the
JSON escape \\ud800) is answered 400 before a key is admitted.

Write-ahead. The end entry is written after the provider answers, because it
holds the hash of the reply. So `reach` first appends `endpoint_call_started`
(gateway_calls) and commits it to the disk; only then does the request leave.
A gateway that stops between contact and the end entry leaves the started
entry, which `flywheel gateway-ledger verify` reports as an unsettled call.
When the started entry cannot be written the request is refused with 503 and
nothing is sent.

`Call` is the same accounting without a `Turn`. Every other route that runs
a model at a roster endpoint uses it through
`endpoint_ledgered.LedgeredProposer` or `endpoint_ledgered.recorded`, and
/v1/embeddings uses it directly. Which routes those are is not kept in a
list here: `gateway_reach` gives a proposer built with no ledger the
gateway's, and makes the transports refuse a model request for which no
`Call` is open.
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from . import gateway_calls as _calls, gateway_turn as _turn

_LOG = logging.getLogger(__name__)
_CONTACT = contextvars.ContextVar("flywheel_gateway_contact", default=None)
UNBILLED = "unbilled"                   # what `contacting()` returns inside `unbilled`
COUNT_PATH = "/v1/messages/count_tokens"    # the only path `unbilled` will contact
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


def unbilled(send, url: str):
    """Contact an upstream for a request that is not billed and not recorded.

    Only token counting is: `url` must end in `/v1/messages/count_tokens`, the
    Claude API route its documentation calls free to use
    (https://platform.claude.com/docs/en/build-with-claude/token-counting,
    "Pricing and rate limits", read 2026-11-14). It creates no message and
    rejects server tools and the MCP connector. Any other URL is refused here,
    before `send` is called."""
    if not str(url).split("?", 1)[0].endswith(COUNT_PATH):
        raise RuntimeError("only a token-count request may contact an upstream outside an "
                           "account; nothing was sent")
    token = _CONTACT.set(UNBILLED)
    try:
        return send()
    finally:
        _CONTACT.reset(token)


class Call:
    """The accounting of one provider call. States: open, contacted, closed.

    `base` holds the entry fields known before contact (endpoint, interface,
    prompt_sha, the caller's fields). `reserved` is what a virtual key's call
    reserved at admission; it goes into the started entry."""

    def __init__(self, ledger, base: dict, reserved=None):
        if ledger is None:
            raise RuntimeError("the gateway ledger is unavailable; nothing was sent upstream")
        self.ledger, self.base, self.reserved = ledger, dict(base), reserved
        self.state, self.call = "open", ""

    def begun(self) -> None:
        """The started entry is in the ledger. `Account` also names the call on its turn."""

    def reach(self, send):
        """Contact the upstream: call `send` and return what it returns.

        The first contact of a call appends its started entry first. When that
        fails the call is refused (503) and `send` is not called."""
        if self.state == "closed":
            raise RuntimeError("this call is already recorded; it cannot contact an upstream")
        if self.state == "open":
            try:
                self.call = _calls.begin(self.ledger, self.base, self.reserved)
            except Exception as exc:    # noqa: BLE001 - no started entry, no contact
                _LOG.error("gateway call to %s refused: its start could not be recorded "
                           "(%s)", self.base.get("endpoint"), type(exc).__name__)
                raise _turn.UpstreamFailed(_calls.TEXT, status=503, reason="ledger_unavailable",
                                           headers={"retry-after": "5"}) from exc
            self.base["call"] = self.call
            self.begun()
        self.state = "contacted"
        token = _CONTACT.set(self)
        try:
            return send()
        finally:
            _CONTACT.reset(token)

    def end(self, kind: str, content: str, meta: dict) -> None:
        """Append the end entry of a call that was contacted. A refused entry is kept
        for the ledger's resume (gateway_calls.defer) and the error is raised."""
        self.state = "closed"
        meta = {**self.base, **meta}
        try:
            with _turn._APPEND:
                self.ledger.append(kind, content, meta)
        except Exception:
            _calls.defer(self.ledger, kind, content, meta)
            raise


class Account(Call):
    """The accounting of one model-interface turn."""

    def __init__(self, ledger, upstream, turn):
        from .gateway_key_gate import OWNER
        if ledger is None:
            raise RuntimeError("the gateway ledger is unavailable; nothing was sent upstream")
        self.upstream, self.turn = upstream, turn
        self.caller = getattr(turn, "caller", None) or OWNER
        try:
            turn.text_form()            # kept on the turn: nothing later flattens it again
            base = {"endpoint": upstream.name, "interface": turn.interface,
                    "prompt_sha": _turn.prompt_sha(turn), **self.caller.meta}
            if not encodable(base):
                raise UnicodeError("a ledger field is not valid UTF-8")
        except UnicodeError as exc:
            raise _turn.TurnRefused("invalid", TEXT) from exc
        super().__init__(ledger, base, getattr(self.caller, "ticket", None))

    def begun(self) -> None:
        self.turn.call = self.call      # gateway_turn puts it in every end entry

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
        except Exception as again:      # noqa: BLE001 - kept for the resume; the client is told
            _calls.defer(self.ledger, "endpoint_call_failed", reason, meta)
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
