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
    return os.environ.get(env_name, "")


def _guard(transport, method, url, headers, body, timeout, name):
    try:
        return transport(method, url, headers, body, timeout)
    except (urllib.error.URLError, OSError, ConnectionError) as e:
        raise BackendError(f"{name} unreachable: {e}") from e
