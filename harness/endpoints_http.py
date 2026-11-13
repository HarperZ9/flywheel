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
import urllib.error
import urllib.request

from .local_agent import BackendError
from .provider_fault_boundary import body_from_http_error, format_provider_fault


def _http(method, url, headers, body, timeout):
    """(method,url,headers,body,timeout)->(status,json). Injectable for tests."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, body_from_http_error(e)


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
        raise BackendError(f"{name} unreachable: {e}") from e


def _response_error(name: str, status, obj, *, kind: str = "") -> BackendError:
    """A response with no completion. The message is the redacted one-line
    fault reading, so a credential a provider echoes back never reaches a log.
    The status and the body ride on the error unredacted, so a caller can read
    the provider's own error fields."""
    error = BackendError(format_provider_fault(name, status, obj, kind=kind or name))
    error.status, error.body = status, obj
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
