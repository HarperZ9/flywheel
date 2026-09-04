"""endpoints_http.py -- shared transport helpers for provider backends.

One injectable HTTP boundary (_http), one credential reader (_k), and one
typed network guard (_guard) shared by every backend module, so a test or
an operator can swap the transport exactly once.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .local_agent import BackendError


def _http(method, url, headers, body, timeout):
    """(method,url,headers,body,timeout)->(status,json). Injectable for tests."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except json.JSONDecodeError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:300]}


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
