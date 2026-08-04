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
"""
from __future__ import annotations

import json
import urllib.request

try:
    from . import providers
except ImportError:                     # standalone run beside the package
    import providers  # type: ignore

# The built-in serve tier is OpenAI-shaped too but lives outside REGISTRY.
_SERVE = ("http://127.0.0.1:8765", "", "14b-cpt")


def _spec(name: str) -> "tuple[str, str, str] | None":
    """(base_url, api_key_env, default_model) for an OpenAI-shaped endpoint."""
    spec = providers.REGISTRY.get(name)
    if spec is not None:
        return spec.base_url, spec.api_key_env, spec.default_model
    if name == "serve":
        return _SERVE
    return None


def _credential(key_env: str) -> str:
    """Env first, OS keychain second; '' when neither (value never logged)."""
    try:
        from .keychain import resolve_credential
        return resolve_credential(key_env)
    except Exception:
        import os
        return os.environ.get(key_env or "", "")


def _default_only(name: str, default_model: str, reason: str) -> dict:
    models = [{"id": default_model, "default": "true"}] if default_model else []
    return {"endpoint": name, "models": models, "reason": reason}


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
        return _native_or_unknown(name)
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


def _native_or_unknown(name: str) -> dict:
    """Endpoints without an OpenAI listing surface (anthropic, gemini, CLI
    tiers) still report their roster default; a name the roster has never
    heard of reports itself unknown."""
    try:
        from .endpoint_registry import unified_roster
        rows = unified_roster().get("endpoints", [])
    except Exception:
        rows = []
    entry = next((e for e in rows if e.get("name") == name), None)
    if entry is None:
        return {"endpoint": name, "models": [],
                "reason": f"unknown endpoint {name!r}"}
    return _default_only(
        name, str(entry.get("default_model", "")),
        "listing unavailable: endpoint has no OpenAI-compatible listing surface")
