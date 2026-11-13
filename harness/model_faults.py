"""model_faults.py -- what a provider said when a call did not succeed.

model_usage reads a call that worked. This reads one that did not, and the
reading is harder than it looks, because the surfaces disagree about where the
error lives, what the numbers beside it mean, and whether the HTTP status line
can be trusted at all. Four wire facts, each read out of a primary source on
2026-09-11 and then put through a pass that tried to overturn it:

- TWO CLOCKS, NEVER INTERCHANGEABLE. A retry-after is a relative duration and a
  ratelimit-reset is an absolute instant, and OpenAI spells its reset family in
  Go durations where Anthropic spells its own in RFC 3339. One parser across
  those turns three hundred and sixty seconds into six. That reading lives in
  model_deadlines, which keeps the two bases on separate keys so a caller that
  reaches for the wrong one raises rather than waiting a wrong wait.
- THE STATUS LINE IS NOT ALWAYS THE STATUS. OpenRouter documents that
  ``error.code`` equals the HTTP status only when the request itself was
  invalid or the account is out of credits, and that every other failure
  arrives on an HTTP 200 with the error in the body or an SSE event. So the
  status is taken from the transport and the body's code is recorded beside it.
- THE BODY IS NOT ALWAYS AN OBJECT. Gemini's ``:streamGenerateContent``
  without ``?alt=sse`` wraps the error in a ONE-ELEMENT ARRAY. Live-probed
  2026-09-11: that call answered ``[{"error": {...}}]``. A reader looking for a
  dict finds none and reports a clean call.
- ONE SERVER, TWO ENVELOPES. ollama answers a local model with a bare string
  under ``error`` and a status it generated itself. On the cloud-model branch
  it relays the upstream status verbatim and the body becomes
  ``{"StatusCode": int, "Status": str, "error": str}``. That relayed status is
  unbounded and includes 429, which the local branch never produces.

Every vendor type and code enumeration is OPEN. A value this module has not
read classifies UNKNOWN with retriable None, so the caller decides rather than
inheriting a guess.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

from typing import Any

from . import model_deadlines, model_redaction

AUTH = "auth"
PERMISSION = "permission"
NOT_FOUND = "not_found"
INVALID_REQUEST = "invalid_request"
TOO_LARGE = "too_large"
RATE_LIMIT = "rate_limit"
QUOTA = "quota"
OVERLOADED = "overloaded"
SERVER_ERROR = "server_error"
TIMEOUT = "timeout"
CONFLICT = "conflict"
TRANSPORT = "transport"
UNKNOWN = "unknown"

# Three-state on purpose. False is a claim that retrying cannot help, and
# spending it on a case nobody has established turns a transient outage into a
# permanent failure. CONFLICT is None because the two authorities disagree:
# Anthropic's own client retries 409 by default with the comment "Retry on lock
# timeouts", while the vendor's error page says to resolve the conflict first.
# TRANSPORT is None because a request that never reached a server may or may
# not have been applied, and that is the caller's risk to weigh.
RETRIABLE = {
    AUTH: False, PERMISSION: False, NOT_FOUND: False, INVALID_REQUEST: False,
    TOO_LARGE: False, QUOTA: False,
    RATE_LIMIT: True, OVERLOADED: True, SERVER_ERROR: True, TIMEOUT: True,
    CONFLICT: None, TRANSPORT: None, UNKNOWN: None,
}

OBJECT = "object"
ARRAY_WRAPPED = "array_wrapped"
BARE_STRING = "bare_string"
RELAYED = "relayed"

_FIELD_KEYS = ("type", "code", "error_type", "status", "param", "details",
               "metadata")


def _record(envelope: str, shape: str, message: Any, fields: dict,
            upstream: Any, reason: Any, body_status: Any) -> dict:
    return {"envelope": envelope, "shape": shape,
            "message": message if isinstance(message, str) else None,
            "fields": fields,
            "upstream_status": upstream if type(upstream) is int else None,
            "upstream_reason": reason if isinstance(reason, str) else None,
            "body_status": body_status if type(body_status) is int else None}


def error_body(body: Any) -> "dict | None":
    """The error a response carried, with the envelope it arrived in, or None.

    The array unwrap happens first because it has to: Gemini's non-SSE
    streaming endpoint returns the error inside a one-element list, and every
    later step here looks for a dict.
    """
    envelope = OBJECT
    if isinstance(body, list) and len(body) == 1:
        body, envelope = body[0], ARRAY_WRAPPED
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, str):
        relayed = type(body.get("StatusCode")) is int
        return _record(envelope, RELAYED if relayed else BARE_STRING, error,
                       {}, body.get("StatusCode"), body.get("Status"), None)
    if not isinstance(error, dict):
        return None
    fields = {key: error[key] for key in _FIELD_KEYS if key in error}
    return _record(envelope, OBJECT, error.get("message"), fields,
                   None, None, body.get("status"))


_BY_STATUS = {400: INVALID_REQUEST, 401: AUTH, 402: QUOTA, 403: PERMISSION,
              404: NOT_FOUND, 408: TIMEOUT, 409: CONFLICT, 413: TOO_LARGE,
              422: INVALID_REQUEST, 429: RATE_LIMIT, 500: SERVER_ERROR,
              502: SERVER_ERROR, 503: OVERLOADED, 504: TIMEOUT,
              529: OVERLOADED}

# Narrow on purpose. insufficient_quota is the one spend marker read out of a
# primary source; an unrecognized 429 therefore stays RATE_LIMIT rather than
# being promoted to a terminal verdict on a guess. Gemini's RESOURCE_EXHAUSTED
# is deliberately absent: google.rpc uses it for pace and for spend alike, so
# it cannot separate them and is UNKNOWN as a discriminator.
QUOTA_MARKS = frozenset({"insufficient_quota"})
TOO_LARGE_MARKS = frozenset({"context_length_exceeded", "max_tokens_exceeded",
                             "token_limit_exceeded", "string_too_long"})
AUTH_MARKS = frozenset({"invalid_api_key", "authentication_error"})


def _marks(error: Any) -> set:
    """Lowercased type and code values, wherever this vendor put them.

    OpenRouter's Responses skin does not give these codes one key path, and its
    Anthropic skin makes error_type optional with error.type underneath, so the
    read is over every field rather than one.
    """
    out = set()
    fields = error.get("fields") if isinstance(error, dict) else None
    for key in ("type", "code", "error_type", "status"):
        value = (fields or {}).get(key)
        if isinstance(value, str) and value:
            out.add(value.lower())
    return out


def classify(status: Any, error: Any, *, transport: str = "http") -> str:
    """A category for one failure, from the transport status and the body.

    ``status`` is what the TRANSPORT reported and never a number lifted out of
    the body. A body code read as the status line reports a live failure as a
    success on any surface that answers 200 with an error inside.

    On a websocket an unrecognized 400 stays UNKNOWN. Every realtime example
    carries status 400 with type invalid_request_error, including conditions
    whose documented remedy is to reconnect, so the usual rule that a 4xx is
    terminal does not hold on that transport.
    """
    marks = _marks(error)
    if marks & QUOTA_MARKS:
        return QUOTA
    if marks & TOO_LARGE_MARKS:
        return TOO_LARGE
    if marks & AUTH_MARKS:
        return AUTH
    if type(status) is not int:
        return TRANSPORT if error is None else UNKNOWN
    known = _BY_STATUS.get(status)
    if known == INVALID_REQUEST and transport == "websocket":
        return UNKNOWN
    if known is not None:
        return known
    if 500 <= status < 600:
        return SERVER_ERROR
    return UNKNOWN


def should_retry_header(headers: Any) -> "bool | None":
    """The provider's own instruction, or None if it gave none.

    Anthropic sends x-should-retry and its client reads that before any status
    test. An explicit instruction outranks a category inferred from a number,
    in both directions.
    """
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == "x-should-retry":
            text = str(value).strip().lower()
            return True if text == "true" else False if text == "false" else None
    return None


def capture(*, status: Any = None, headers: Any = None, body: Any = None,
            dialect: str = "", kind: str = "", transport: str = "http") -> dict:
    """One failed call, as observed at the boundary.

    Text is scrubbed before it is kept. A 401 body says "Incorrect API key
    provided" and then prints the key, so the message that reaches a durable
    record would carry the live credential it is a record of.
    """
    error = error_body(body)
    category = classify(status, error, transport=transport)
    told = should_retry_header(headers)
    retry = RETRIABLE.get(category)
    source = "category"
    if told is not None and category not in (AUTH, PERMISSION, QUOTA):
        retry, source = told, "provider_header"
    scrubbed = model_redaction.scrub(error["message"] if error else None)
    fields = model_redaction.scrub_value(error["fields"] if error else {})
    reason = None
    reason_reading = {"kinds": [], "truncated": False}
    if error and error.get("upstream_reason") is not None:
        reason_reading = model_redaction.scrub(error["upstream_reason"])
        reason = reason_reading["text"]
    deadlines = model_redaction.scrub_value(
        model_deadlines.read(headers, dialect=dialect))
    redacted_kinds = []

    def note(reading: dict) -> None:
        for redacted_kind in reading.get("kinds", []):
            if redacted_kind not in redacted_kinds:
                redacted_kinds.append(redacted_kind)

    note(scrubbed)
    note(fields)
    note(reason_reading)
    note(deadlines)
    caveats = []
    clean_fields = fields["value"] if isinstance(fields["value"], dict) else {}
    code = clean_fields.get("code")
    if kind == "openrouter":
        caveats.append("OPENROUTER_CODE_IS_NOT_THE_STATUS_LINE")
    if error and error["shape"] == RELAYED:
        caveats.append("OLLAMA_RELAYED_UPSTREAM_STATUS")
    if error and error["envelope"] == ARRAY_WRAPPED:
        caveats.append("ARRAY_WRAPPED_BODY")
    body_truncated = isinstance(body, dict) and body.get("body_truncated") is True
    return {
        "dialect": dialect or None, "kind": kind or None,
        "transport": transport,
        "status": status if type(status) is int else None,
        "category": category, "retriable": retry, "retriable_source": source,
        "provider_said_retry": told,
        "message": scrubbed["text"], "redacted": bool(redacted_kinds),
        "redacted_kinds": redacted_kinds,
        "bounded": (scrubbed["truncated"] or fields["bounded"]
                    or reason_reading["truncated"] or deadlines["bounded"]
                    or body_truncated),
        "fields": clean_fields, "body_code": code,
        # Two more numbers that are not the status line. body_status is a
        # top-level integer some 401 bodies carry beside error, upstream_status
        # is what ollama relayed from the host that actually refused.
        "body_status": (error or {}).get("body_status"),
        "upstream_status": (error or {}).get("upstream_status"),
        "upstream_reason": reason,
        "envelope": (error or {}).get("envelope"),
        "shape": (error or {}).get("shape"),
        "deadlines": deadlines["value"],
        "caveats": caveats,
    }


__all__ = ["ARRAY_WRAPPED", "AUTH", "AUTH_MARKS", "BARE_STRING", "CONFLICT",
           "INVALID_REQUEST", "NOT_FOUND", "OBJECT", "OVERLOADED",
           "PERMISSION", "QUOTA", "QUOTA_MARKS", "RATE_LIMIT", "RELAYED",
           "RETRIABLE", "SERVER_ERROR", "TIMEOUT", "TOO_LARGE",
           "TOO_LARGE_MARKS", "TRANSPORT", "UNKNOWN", "capture", "classify",
           "error_body", "should_retry_header"]
