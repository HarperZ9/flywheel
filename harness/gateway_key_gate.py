"""gateway_key_gate.py -- who is calling a model interface, and may the call run.

The gateway's own token is the owner: no budget, attributed to `owner`. A
virtual key (gateway_keys) is a named caller with limits. This module is the
only place the two meet the HTTP handler:

  admits(handler, path)   called by `gateway.py` `_authorized`. True only for a
                          POST to a path in gateway_interfaces.PATHS, from an
                          allowed Host, with a JSON content type, carrying a
                          key the credential store holds and that is not
                          revoked. Any other route never sees a virtual key.
  enter(handler, ...)     called by gateway_interfaces.serve before anything is
                          sent upstream. Returns the caller, and a refusal
                          `Response` when the model is off the key's allow-list
                          or its totals are at or over a limit.
  Bill(turn, reply)       what one served call costs its key: the provider's
                          counts, or the word estimate when it sent none.

The limit check reads the totals so far. A call that starts under the limit
runs to the end, so one call can cross a limit; the next one is refused.

Refusals, in each interface's documented error shape:
  Messages    limit: 400 invalid_request_error (the Claude API errors page says
              a reached spend limit returns 400); model: 403 permission_error;
              key: 401 authentication_error.
              https://platform.claude.com/docs/en/api/errors, read 2026-11-14
  Responses   limit: 429 with type insufficient_quota and code
              key_budget_exceeded (the error-codes guide lists spend limits
              under 429 and says the broader error.type can be
              insufficient_quota); model: 403, code model_not_allowed; key:
              401, code invalid_api_key.
              https://developers.openai.com/api/docs/guides/error-codes, read
              2026-11-14
A limit refusal carries `x-should-retry: false`: a retry cannot succeed.

No message, log record or ledger entry here contains a key. A refusal names
the key by its name; the ledger also carries its fingerprint.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from hmac import compare_digest

from . import gateway_keys

_LOG = logging.getLogger(__name__)
OWNER_NAME = "owner"
_INTERFACES = {"/v1/responses": "openai-responses"}
_CODES = {401: "invalid_api_key", 403: "model_not_allowed", 429: "key_budget_exceeded"}
_JSON = "application/json"


@dataclass
class Caller:
    name: str = OWNER_NAME
    fingerprint: str = ""
    row: "dict | None" = None           # None for the owner
    keys: object = None

    @property
    def meta(self) -> dict:
        if self.row is None:
            return {"key": self.name}
        return {"key": self.name, "key_fp": self.fingerprint}


OWNER = Caller()


def open_keys(home):
    """The key store of a Flywheel home. Tests replace this with a fake store."""
    return gateway_keys.Keys(home)


def offered(headers) -> str:
    auth = headers.get("Authorization", "") or ""
    return auth[7:] if auth.startswith("Bearer ") else (headers.get("x-api-key", "") or "")


def _find(handler):
    """The caller for the key this request carries, or None. Never raises."""
    given = offered(handler.headers)
    if not given.startswith(gateway_keys.PREFIX):
        return None
    try:
        keys = open_keys(handler.flywheel_home)
        found = keys.authenticate(given)
    except Exception as exc:   # noqa: BLE001 - a broken store admits nobody
        _LOG.warning("gateway key lookup failed (%s); the request was not admitted",
                     type(exc).__name__)
        return None
    if found is None:
        return None
    return Caller(found[0], found[1]["fingerprint"], found[1], keys)


def admits(handler, path: str) -> bool:
    """Does this request carry a live virtual key on a model interface path?"""
    from .gateway_interfaces import PATHS
    if path not in PATHS:
        return False
    handler.virtual_key = None
    from .gateway_auth import _host_of
    ctype = (handler.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
    if (handler.command != "POST" or ctype != _JSON
            or _host_of(handler.headers) not in handler.allowed_hosts):
        return False
    found = _find(handler)
    if found is None or found.row.get("revoked"):
        return False
    handler.virtual_key = found
    return True


def _caller(handler) -> "Caller | None":
    """The owner, the key `admits` found, or None for a credential that is neither."""
    found, handler.virtual_key = getattr(handler, "virtual_key", None), None
    if found is not None:
        return found
    given, token = offered(handler.headers), getattr(handler, "auth_token", None)
    if token and given and compare_digest(given.encode("utf-8"), token.encode("utf-8")):
        return OWNER
    if not token and not given.startswith(gateway_keys.PREFIX):
        return OWNER                    # the gateway runs with authentication off
    return None


def _refusal(path: str, status: int, text: str, budget: bool = False) -> object:
    from .gateway_turn import Response
    extra = {"x-should-retry": "false"} if budget else {}
    if path == "/v1/responses":
        from .gateway_responses_reply import error
        body = error(status, text, "model" if status == 403 else None, _CODES.get(status))
        if budget:
            body["error"]["type"] = "insufficient_quota"
        return Response(status, body, headers={
            "x-request-id": f"req_fw_{uuid.uuid4().hex[:24]}", **extra})
    from .gateway_messages_wire import error
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    return Response(status, error(status, text, request_id),
                    headers={"request-id": request_id, **extra})


def _check(caller: Caller, model) -> "tuple | None":
    """(reason, status, sentence) when the key may not make this call."""
    from .provider_fault_boundary import redacted_text
    row, name = caller.row, caller.name
    allowed = row.get("models") or []
    if allowed and isinstance(model, str) and model not in allowed:
        return "model_not_allowed", 403, (
            f"gateway key '{name}' may not use the model "
            f"{redacted_text(model, limit=80)!r}; its allow-list is {', '.join(allowed)}")
    limit = gateway_keys.over(row)
    if limit is not None:
        return limit[0], 0, (f"gateway key '{name}' has reached {limit[1]}; zero its counters "
                             f"with `flywheel gateway-key reset {name}` or create a key with "
                             "a higher limit")
    return None


def enter(handler, path: str, body, ledger) -> tuple:
    """(caller, None) to go on, or (caller, Response) to refuse before any upstream call."""
    caller = _caller(handler)
    if caller is None:
        return None, _refusal(path, 401, "the credential is not the gateway token or a "
                              "live gateway key")
    if caller.row is None:
        return caller, None
    refused = _check(caller, body.get("model") if isinstance(body, dict) else None)
    if refused is None:
        return caller, None
    reason, status, text = refused
    interface = _INTERFACES.get(path, "anthropic-messages")
    budget = status == 0
    if budget:
        status = 429 if path == "/v1/responses" else 400
    _LOG.info("gateway %s request refused for key %s (%s)", interface, caller.name, reason)
    if ledger is not None:
        from .gateway_turn import _APPEND
        with _APPEND:
            ledger.append("endpoint_call_refused", reason,
                          {"interface": interface, **caller.meta, "reason": reason})
    return caller, _refusal(path, status, text + ". Nothing was sent upstream.", budget)


class Bill:
    """What one served call costs its caller. The owner is never charged."""

    def __init__(self, turn, reply):
        self.caller = getattr(turn, "caller", None) or OWNER
        self.meta, self.counts, self.estimated = dict(self.caller.meta), None, False
        if self.caller.row is None:
            return
        self.estimated = not reply.usage_reported
        if self.estimated:
            from . import gateway_turn, token_usage
            system, prompt = turn.text_form()
            words = token_usage.estimate(f"{system}\n{prompt}", gateway_turn.reply_text(reply))
            self.counts = {"input": words["prompt_words"], "output": words["completion_words"]}
            self.meta["estimated"] = True
        else:
            self.counts = {key: reply.usage.get(key) or 0 for key in gateway_keys.COUNTS}
        self.meta["charged_tokens"] = sum(self.counts.values())

    def settle(self) -> None:
        """Debit the key. A call that cannot be charged is not served."""
        if self.counts is None:
            return
        try:
            self.caller.keys.debit(self.caller.name, self.counts, self.estimated)
        except gateway_keys.KeysError as exc:
            raise RuntimeError(f"the call could not be charged to gateway key "
                               f"'{self.caller.name}'; the reply was not served") from exc
