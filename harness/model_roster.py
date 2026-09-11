"""model_roster.py -- which models an endpoint can serve, honestly.

Every ProviderSpec names ONE default_model, and until now the app had no way
to see past it. OpenAI-compatible endpoints (ollama, serve, every REGISTRY
entry) expose GET {base_url}/models; this module asks, folds the answer into
a stable payload, and never raises: an unreachable lister, an absent
credential, or a native endpoint with no listing surface all degrade to the
spec's default plus a plain-language reason. The default is ALWAYS present
and flagged, so a picker can render before, during, and after any failure.

Payload shape (no floats, JSON-safe):
  {"endpoint": name,
   "models": [{"id": str, "default": "true"|"false"}, ...],
   "reason": ""              # or "credential absent" / "listing unavailable: ..."
  }

Native Anthropic adds optional metadata so callers can distinguish the
configured default from provider-listed catalog rows. Catalog presence is not
inference availability and is not proof of native-tool capability.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from . import providers
except ImportError:                     # standalone run beside the package
    import providers  # type: ignore

# The built-in serve tier is OpenAI-shaped too but lives outside REGISTRY.
_SERVE = ("http://127.0.0.1:8765", "", "14b-cpt")
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,159}\Z")
_SECRET_LIKE_RE = re.compile(r"(?i)^(sk-|bearer|api[_-]?key)")
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_PAGE_LIMIT = 100
_ANTHROPIC_MAX_PAGES = 5
_ANTHROPIC_MAX_RESPONSE_BYTES = 262_144


class _RosterPublicError(Exception):
    """A sanitized, UI-safe listing failure."""


def _spec(name: str) -> "tuple[str, str, str] | None":
    """(base_url, api_key_env, default_model) for an OpenAI-shaped endpoint."""
    spec = providers.REGISTRY.get(name)
    if spec is not None:
        return spec.base_url, spec.api_key_env, spec.default_model
    if name == "serve":
        return _SERVE
    return None


def _native_spec(name: str) -> "tuple[str, str, str, str, str] | None":
    """One row from endpoint_registry._NATIVE without building unified_roster."""
    try:
        from .endpoint_registry import _NATIVE
    except Exception:
        _NATIVE = ()  # type: ignore
    for row in _NATIVE:
        if row[0] == name:
            return row
    return None


def _credential(key_env: str) -> str:
    """Env first, OS keychain second; '' when neither (value never logged)."""
    try:
        from .keychain import resolve_credential
        return resolve_credential(key_env)
    except Exception:
        import os
        return os.environ.get(key_env or "", "")


def _default_only(name: str, default_model: str, reason: str, **extra) -> dict:
    models = [{"id": default_model, "default": "true"}] if default_model else []
    out = {"endpoint": name, "models": models, "reason": reason}
    out.update(extra)
    return out


def _safe_model_id(value) -> str:
    if not isinstance(value, str) or not _MODEL_ID_RE.fullmatch(value):
        return ""
    if _SECRET_LIKE_RE.match(value):
        return ""
    return value


def _fetch_ids(base_url: str, key: str, timeout: float) -> list[str]:
    """The model ids a live /models listing reports, in server order."""
    req = urllib.request.Request(base_url.rstrip("/") + "/models")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8", "replace"))
    ids: list[str] = []
    for row in (body.get("data") or []) if isinstance(body, dict) else []:
        mid = row.get("id") if isinstance(row, dict) else None
        if isinstance(mid, str) and mid and mid not in ids:
            ids.append(mid)
    return ids


def list_models(endpoint: str, *, timeout: float = 3.0) -> dict:
    """The endpoint's model roster: default always present and flagged; a
    live OpenAI-style listing appended when reachable; failure is a reason
    string, never an exception."""
    name = (endpoint or "").strip()
    spec = _spec(name)
    if spec is None:
        return _native_or_unknown(name, timeout=timeout)
    base_url, key_env, default_model = spec
    if not base_url:
        return _default_only(name, default_model,
                             "listing unavailable: no base_url configured")
    key = ""
    if key_env:
        key = _credential(key_env)
        if not key:
            return _default_only(name, default_model, "credential absent")
    try:
        ids = _fetch_ids(base_url, key, timeout)
    except Exception as e:
        return _default_only(
            name, default_model, f"listing unavailable: {type(e).__name__}: {e}")
    models = [{"id": default_model, "default": "true"}] if default_model else []
    models += [{"id": m, "default": "false"} for m in ids if m != default_model]
    return {"endpoint": name, "models": models, "reason": ""}


def _native_or_unknown(name: str, *, timeout: float) -> dict:
    """Native endpoint roster without the full unified_roster side effects."""
    native = _native_spec(name)
    if native is None:
        return {"endpoint": name, "models": [],
                "reason": f"unknown endpoint {name!r}"}
    native_name, kind, key_env, _host, default_model = native
    if native_name == "anthropic":
        return _anthropic_models(native_name, key_env, default_model, timeout)
    return _default_only(
        name, default_model,
        "listing unavailable: endpoint has no OpenAI-compatible listing surface")


def _anthropic_models(name: str, key_env: str, default_model: str,
                      timeout: float) -> dict:
    meta = {
        "provider_listed_models": [],
        "default_model_source": "configured",
        "default_provider_listed": None,
        "availability": "not_checked",
        "availability_note": "provider catalog presence is not inference availability or strict tool capability proof",
    }
    key = _credential(key_env)
    if not key:
        return _default_only(name, default_model, "credential absent", **meta)
    try:
        ids, warning = _fetch_anthropic_ids(key, timeout)
    except Exception as e:
        return _default_only(name, default_model,
                             f"listing unavailable: {_safe_error(e)}", **meta)
    models = [{"id": default_model, "default": "true"}] if default_model else []
    models += [{"id": mid, "default": "false"}
               for mid in ids if mid != default_model]
    listed = bool(default_model and default_model in ids)
    reason_parts = [warning] if warning else []
    if default_model and not listed:
        reason_parts.append("configured default not listed by provider catalog")
    return {"endpoint": name, "models": models,
            "reason": "; ".join(reason_parts),
            "provider_listed_models": ids,
            "default_model_source": "configured",
            "default_provider_listed": listed,
            "availability": "provider_catalog_only",
            "availability_note": "provider catalog presence is not inference availability or strict tool capability proof"}


def _fetch_anthropic_ids(key: str, timeout: float) -> "tuple[list[str], str]":
    deadline = time.monotonic() + max(float(timeout), 0.001)
    ids: list[str] = []
    after_id = ""
    for _page in range(_ANTHROPIC_MAX_PAGES):
        params = {"limit": str(_ANTHROPIC_PAGE_LIMIT)}
        if after_id:
            params["after_id"] = after_id
        url = _ANTHROPIC_MODELS_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("X-api-key", key)
        req.add_header("anthropic-version", _ANTHROPIC_VERSION)
        with _open_anthropic(req, _remaining(deadline)) as resp:
            body = _read_json_limited(resp)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise _RosterPublicError("invalid response")
        for row in data:
            mid = _safe_model_id(row.get("id") if isinstance(row, dict) else None)
            if mid and mid not in ids:
                ids.append(mid)
        if body.get("has_more") is not True:
            return ids, ""
        next_id = _safe_model_id(body.get("last_id"))
        if not next_id:
            return ids, "listing truncated: invalid cursor"
        after_id = next_id
    return ids, "listing truncated: page cap reached"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _open_anthropic(req, timeout):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(req, timeout=timeout)


def _read_json_limited(resp) -> dict:
    raw = resp.read(_ANTHROPIC_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _ANTHROPIC_MAX_RESPONSE_BYTES:
        raise _RosterPublicError("response too large")
    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        raise _RosterPublicError("invalid JSON") from None
    if not isinstance(body, dict):
        raise _RosterPublicError("invalid response")
    return body


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _RosterPublicError("deadline exceeded")
    return remaining


def _safe_error(e: Exception) -> str:
    if isinstance(e, _RosterPublicError):
        return str(e)
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    return type(e).__name__
