"""endpoints_http.py -- shared transport helpers for provider backends.

One injectable HTTP boundary (_http), one credential reader (_k), one
typed network guard (_guard) and one error for a response with no
completion (_response_error), shared by every backend module, so a test or
an operator can swap the transport exactly once. The strict parser for one
native tool call (_parse_tool_call) lives here too.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

from .local_agent import BackendError
from .model_redaction import scrub_value
from .provider_fault_boundary import (body_from_http_error, limit_fields,
                                      read_provider_fault, redacted_text)

# The transport contract is (status, json) and every injected transport and
# budget wrapper relies on that pair, so a failed response's headers cannot ride
# in the return. They wait here, per thread, beside the exact body object they
# arrived with, and _response_error takes them only for that same object.
_FAULT = threading.local()


def _http(method, url, headers, body, timeout):
    """(method,url,headers,body,timeout)->(status,json). Injectable for tests."""
    _FAULT.last = None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        obj = body_from_http_error(e)
        _FAULT.last = (obj, _header_map(getattr(e, "headers", None)))
        return e.code, obj


def _header_map(headers) -> dict:
    items = getattr(headers, "items", None)
    return {str(k): v for k, v in items()} if callable(items) else {}


def _fault_headers(obj) -> dict:
    """The headers of the failed response whose body is ``obj``, read once.

    Identity, not equality: two failures can carry equal bodies and different
    retry deadlines, and a deadline must never move from one to the other."""
    last, _FAULT.last = getattr(_FAULT, "last", None), None
    return last[1] if last is not None and last[0] is obj else {}


def _k(env_name: str) -> str:
    """The credential for a backend: env first, OS keychain second, '' when
    neither -- the same order `keychain.resolve_credential` documents and every
    other consumer already used.

    This reader is what the dispatch ladder actually calls. It used to read
    os.environ alone, which split the two halves of the credential surface:
    `unified_roster` and the gateway resolved through the keychain and reported
    a slot as credential-present, while `build_endpoints` looked only at the
    environment, reported `health=False`, and 401'd at dispatch. A key saved
    through `flywheel auth login` or `/api/keychain/set` was therefore visible
    everywhere except the code path that needed it.

    Import is lazy so a stripped deployment without keychain.py still serves
    env-only, matching `gateway._resolve_credential`."""
    if not env_name:
        return ""
    try:
        from .keychain import resolve_credential
        return resolve_credential(env_name)
    except Exception:
        return os.environ.get(env_name, "")


def _guard(transport, method, url, headers, body, timeout, name):
    try:
        return transport(method, url, headers, body, timeout)
    except (urllib.error.URLError, OSError, ConnectionError) as e:
        raise BackendError(f"{name} unreachable: {redacted_text(str(e))}") from e


def _response_error(name: str, status, obj, *, kind: str = "") -> BackendError:
    """A response with no completion. The message is the redacted one-line
    fault reading, with the retry deadline when the response carried one, so a
    credential a provider echoes back never reaches a log.

    Nothing unredacted rides on the error. ``body`` is the provider's body with
    every string scrubbed, ``fault`` is the redacted fault record, and
    ``limit_fields`` holds the error type, code and status a budget reader
    compares by exact value."""
    record, line = read_provider_fault(
        name, status, obj, headers=_fault_headers(obj), kind=kind or name)
    error = BackendError(line)
    error.status, error.fault = status, record
    error.limit_fields = limit_fields(obj)
    error.body = scrub_value(obj)["value"]
    return error


def _parse_tool_call(call: dict) -> dict:
    """One native tool call, parsed strictly: malformed JSON arguments are
    reported, never silently executed with guessed arguments."""
    fn = call.get("function") if isinstance(call, dict) else None
    name = fn.get("name", "") if isinstance(fn, dict) else ""
    raw = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
    parsed: dict = {}
    error = ""
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                error = "arguments are not a JSON object"
        except (json.JSONDecodeError, TypeError):
            error = "arguments are not parseable JSON"
    out = {"id": call.get("id", ""), "name": name, "arguments": parsed}
    if error:
        out["arguments_error"] = error
    return out
