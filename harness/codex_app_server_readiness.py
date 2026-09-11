"""Public projection and bounded route-readiness probe for Codex app-server."""
from __future__ import annotations

import threading

from .codex_app_server_transport import _run, subprocess_run

_READINESS_LOCK = threading.Lock()
_READINESS_BY_CONTEXT: dict[str, dict] = {}
_PUBLIC_STATUS_KEYS = {
    "ok", "state", "authenticated", "account_state", "account_type",
    "auth_mode", "plan_type", "email_present", "requires_openai_auth",
    "source", "cli_present", "executable", "version", "run_ready",
    "run_ready_reason", "route_ready", "route_ready_reason",
    "readiness_check_available", "readiness_checked", "readiness_probe",
    "supervised_run_ready", "note", "error",
}


def apply_cached_readiness(status: dict) -> dict:
    key = readiness_context_key(status)
    if not key or status.get("authenticated") is not True:
        return status
    with _READINESS_LOCK:
        cached = dict(_READINESS_BY_CONTEXT.get(key) or {})
    return {**status, **cached} if cached else status


def _store_readiness(status: dict, readiness: dict) -> dict:
    key = readiness_context_key(status)
    if key:
        with _READINESS_LOCK:
            _READINESS_BY_CONTEXT[key] = dict(readiness)
    return {**status, **readiness}


def invalidate_readiness() -> None:
    with _READINESS_LOCK:
        _READINESS_BY_CONTEXT.clear()


def readiness_context_key(status: dict) -> str:
    if status.get("authenticated") is not True:
        return ""
    parts = [status.get(name, "") for name in (
        "identity", "codex_home", "cwd", "env_fingerprint",
        "account_state", "account_type", "auth_mode")]
    return "\0".join(str(part) for part in parts)


def execution_readiness(status: dict, *, runner=None, timeout: float = 12.0) -> dict:
    if status.get("authenticated") is not True:
        return {**status, "route_ready": False, "run_ready": False,
                "route_ready_reason": "account_not_authenticated",
                "run_ready_reason": "account_not_authenticated",
                "readiness_checked": True, "readiness_probe": "codex_exec_help"}
    prefix = list(status.get("argv_prefix") or [])
    if not prefix:
        return {**status, "route_ready": False, "run_ready": False,
                "route_ready_reason": "cli_unresolved",
                "run_ready_reason": "cli_unresolved",
                "readiness_checked": True, "readiness_probe": "codex_exec_help"}
    runner = runner or subprocess_run
    try:
        proc = _run(runner, [*prefix, "exec", "--help"], timeout,
                    env=status.get("env"), cwd=status.get("cwd"))
    except Exception:
        ok = False
    else:
        ok = getattr(proc, "returncode", 1) == 0
    reason = "codex_exec_help_ok" if ok else "codex_exec_help_failed"
    return _store_readiness(status, {
        "route_ready": ok, "run_ready": ok,
        "route_ready_reason": reason, "run_ready_reason": reason,
        "readiness_checked": True, "readiness_probe": "codex_exec_help",
        "supervised_run_ready": False})


def public_projection(status: dict) -> dict:
    out = {k: status[k] for k in _PUBLIC_STATUS_KEYS if k in status}
    out.setdefault("route_ready", out.get("run_ready") is True)
    out.setdefault("route_ready_reason", out.get("run_ready_reason", ""))
    out.setdefault("run_ready", out.get("route_ready") is True)
    out.setdefault("run_ready_reason", out.get("route_ready_reason", ""))
    out.setdefault("supervised_run_ready", False)
    return out
