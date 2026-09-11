"""Sanitized ChatGPT account state through Codex app-server.

Codex owns tokens and browser/device-code login. Flywheel sends only supported
account JSON-RPC requests over the official app-server transport and returns
presence/status labels, never credentials or raw account metadata.
"""
from __future__ import annotations

import urllib.parse

from .codex_app_server_readiness import (
    apply_cached_readiness,
    execution_readiness,
    invalidate_readiness,
    public_projection,
)
from .codex_app_server_transport import (
    JsonlAppServerClient,
    app_server_env,
    resolve_codex_cli,
)
from .codex_app_server_sessions import LoginSession, close_provider, get, remember

_TRUSTED_SUFFIXES = (".openai.com", ".chatgpt.com")
_TRUSTED_HOSTS = {"openai.com", "chatgpt.com"}

def _sanitize_error(text) -> str:
    msg = str(text or "")
    for marker in ("Bearer ", "sk-", "xoxb-", "xoxp-", "ghp_"):
        if marker in msg:
            msg = msg.split(marker, 1)[0] + marker + "[redacted]"
    parsed = urllib.parse.urlsplit(msg)
    if parsed.scheme and parsed.netloc:
        return "app-server returned an unusable URL"
    return msg[:240]

def _fail(state: str, error: str, **extra) -> dict:
    return {"ok": False, "state": state, "authenticated": False,
            "error": _sanitize_error(error), **extra}

def _trusted_url(value: str) -> bool:
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host in _TRUSTED_HOSTS
        or any(host.endswith(suffix) for suffix in _TRUSTED_SUFFIXES))

def _client(resolution, *, popen=None, base_env=None, cwd=None):
    return JsonlAppServerClient(
        resolution["argv_prefix"], popen=popen,
        env=base_env if base_env is not None else resolution.get("env"),
        cwd=cwd if cwd is not None else resolution.get("cwd"))

def _resolve(resolver, *, base_env=None, cwd=None):
    try:
        return resolver(env=base_env, cwd=cwd)
    except TypeError:
        return resolver()

def _login_mode(mode: str) -> str:
    return "device-code" if str(mode or "").replace("_", "-") == "device-code" else "browser"

def begin_login(*, provider: str = "openai", mode: str = "browser",
                resolver=None, popen=None, base_env=None, cwd=None,
                include_login_id: bool = False) -> dict:
    mode = _login_mode(mode)
    resolver = resolver or resolve_codex_cli
    resolution = _resolve(resolver, base_env=base_env, cwd=cwd)
    if resolution.get("ok") is not True:
        return {"ok": False, "provider": provider, "mode": "codex-app-server",
                "state": resolution.get("state", "unknown"),
                "error": status_label(resolution)}
    login_type = "chatgptDeviceCode" if mode == "device-code" else "chatgpt"
    client = _client(resolution, popen=popen, base_env=base_env, cwd=cwd)
    try:
        client.__enter__()
        result = client.request("account/login/start", {"type": login_type})
    except Exception as exc:
        client.close()
        return {"ok": False, "provider": provider, "mode": mode,
                "error": f"Codex app-server login failed ({type(exc).__name__})"}
    out = _login_response(provider, mode, result, include_login_id=include_login_id)
    login_id = result.get("loginId") if isinstance(result.get("loginId"), str) else ""
    if out.get("ok") and login_id:
        remember(LoginSession(provider=provider, mode=mode, login_id=login_id, client=client))
    else:
        client.close()
    return out

def _login_response(provider, mode, result, *, include_login_id: bool) -> dict:
    if result.get("type") == "chatgptDeviceCode":
        url = result.get("verificationUrl", "")
        if not _trusted_url(url):
            return _fail("untrusted_login_url", "untrusted login URL",
                         provider=provider, mode=mode)
        out = {"ok": True, "provider": provider, "mode": "device-code",
               "verification_url": url,
               "user_code": str(result.get("userCode") or "")[:80]}
    else:
        url = result.get("authUrl", "")
        if not _trusted_url(url):
            return _fail("untrusted_login_url", "untrusted login URL",
                         provider=provider, mode=mode)
        out = {"ok": True, "provider": provider, "mode": "browser",
               "authorize_url": url}
    if include_login_id and isinstance(result.get("loginId"), str):
        out["login_id"] = result["loginId"]
    return out

def _internal_status(*, resolver=None, popen=None, base_env=None, cwd=None,
                     check_execution: bool = False, readiness_runner=None) -> dict:
    resolver = resolver or resolve_codex_cli
    resolution = _resolve(resolver, base_env=base_env, cwd=cwd)
    if resolution.get("ok") is not True:
        status = {**resolution, "authenticated": False,
                "account_state": resolution.get("state", "unknown"),
                "route_ready": False, "run_ready": False,
                "route_ready_reason": resolution.get("state", "unknown"),
                "run_ready_reason": resolution.get("state", "unknown"),
                "readiness_check_available": False,
                "supervised_run_ready": False}
        return execution_readiness(status, runner=readiness_runner) if check_execution else status
    try:
        with _client(resolution, popen=popen, base_env=base_env, cwd=cwd) as c:
            result = c.request("account/read", {"refreshToken": False})
            notifications = list(c.notifications)
            resolution = {**resolution, "codex_home": c.codex_home or resolution.get("codex_home", "")}
    except Exception as exc:
        invalidate_readiness()
        status = {**resolution, "authenticated": False, "account_state": "unknown",
                "route_ready": False, "run_ready": False,
                "route_ready_reason": "account_status_unknown",
                "run_ready_reason": "account_status_unknown",
                "readiness_check_available": False,
                "supervised_run_ready": False,
                "note": f"Codex app-server account status failed ({type(exc).__name__})"}
        return execution_readiness(status, runner=readiness_runner) if check_execution else status
    status = _status_from_account(resolution, result, notifications)
    return execution_readiness(status, runner=readiness_runner) if check_execution else status

def _status_from_account(resolution: dict, result: dict, notifications: list) -> dict:
    account = result.get("account") if isinstance(result, dict) else None
    account = account if isinstance(account, dict) else {}
    account_type = account.get("type")
    authed = account_type == "chatgpt" and result.get("requiresOpenaiAuth") is False
    auth_mode = "chatgpt" if authed else ""
    for msg in notifications:
        params = msg.get("params") if isinstance(msg, dict) else {}
        if isinstance(params, dict) and params.get("authMode") == "chatgpt":
            auth_mode = "chatgpt"
    status = {**resolution, "authenticated": authed,
            "state": "authenticated" if authed else "not_authenticated",
            "account_state": "authenticated" if authed else "not_authenticated",
            "account_type": account_type if account_type in ("chatgpt", "apiKey") else "",
            "auth_mode": auth_mode,
            "plan_type": account.get("planType") if isinstance(account.get("planType"), str) else "",
            "email_present": isinstance(account.get("email"), str),
            "requires_openai_auth": result.get("requiresOpenaiAuth") is True,
            "route_ready": False, "route_ready_reason": "not_checked",
            "run_ready": False, "run_ready_reason": "not_checked",
            "readiness_check_available": authed,
            "readiness_checked": False,
            "readiness_probe": "codex_exec_help",
            "supervised_run_ready": False}
    if not authed:
        invalidate_readiness()
    return apply_cached_readiness(status)

def public_status(*, resolver=None, popen=None, base_env=None, cwd=None,
                  check_execution: bool = False, readiness_runner=None) -> dict:
    return public_projection(_internal_status(
        resolver=resolver, popen=popen, base_env=base_env, cwd=cwd,
        check_execution=check_execution, readiness_runner=readiness_runner))

def cancel_login(*, provider: str = "openai", login_id: str,
                 resolver=None, popen=None, base_env=None, cwd=None) -> dict:
    if not login_id:
        return {"ok": False, "provider": provider, "state": "already_completed",
                "error": "no active Codex app-server login to cancel"}
    session = get(login_id)
    if session is not None:
        return session.cancel()
    resolver = resolver or resolve_codex_cli
    resolution = _resolve(resolver, base_env=base_env, cwd=cwd)
    if resolution.get("ok") is not True:
        return {"ok": False, "provider": provider,
                "error": status_label(resolution)}
    try:
        with _client(resolution, popen=popen, base_env=base_env, cwd=cwd) as c:
            result = c.request("account/login/cancel", {"loginId": login_id})
    except Exception as exc:
        return {"ok": False, "provider": provider,
                "error": f"Codex app-server cancel failed ({type(exc).__name__})"}
    state = result.get("status", "unknown")
    return {"ok": state == "canceled", "provider": provider, "state": state}

def logout(*, provider: str = "openai", resolver=None, popen=None,
           base_env=None, cwd=None) -> dict:
    resolver = resolver or resolve_codex_cli
    resolution = _resolve(resolver, base_env=base_env, cwd=cwd)
    if resolution.get("ok") is not True:
        return {"ok": False, "provider": provider,
                "error": status_label(resolution)}
    try:
        with _client(resolution, popen=popen, base_env=base_env, cwd=cwd) as c:
            c.request("account/logout", {})
    except Exception as exc:
        return {"ok": False, "provider": provider,
                "error": f"Codex app-server logout failed ({type(exc).__name__})"}
    close_provider(provider)
    invalidate_readiness()
    return {"ok": True, "provider": provider, "state": "signed_out"}

def login_status(*, provider: str = "openai", login_id: str) -> dict:
    session = get(login_id)
    if session is None:
        return {"ok": True, "provider": provider, "state": "running"}
    return session.status()

def authenticated_resolution(**kwargs) -> dict:
    status = _internal_status(**kwargs)
    if status.get("authenticated") is not True:
        return _fail(status.get("state", "not_authenticated"),
                     "ChatGPT account sign-in required",
                     **{k: status.get(k) for k in ("argv_prefix", "identity",
                                                   "executable", "version")})
    if status.get("run_ready") is not True:
        return _fail("execution_not_ready", "Codex CLI execution not admitted",
                     **status)
    return {"ok": True, **status}

def verify_authenticated_identity(identity: str, **kwargs) -> dict:
    status = authenticated_resolution(**kwargs)
    if status.get("ok") is not True:
        return status
    if status.get("identity") != identity:
        return _fail("executable_changed",
                     "Codex executable changed before prompt execution")
    return status

def bind_authenticated_backend(backend, *, authenticated=None, verifier=None):
    auth = (authenticated or authenticated_resolution)()
    if auth.get("ok") is not True:
        raise ValueError(status_label(auth))
    from .endpoints import CliBackend
    from .local_agent import BackendError

    argv = list(getattr(backend, "argv", []))
    prefix = list(auth.get("argv_prefix") or [])
    if not prefix or not argv:
        raise ValueError("Codex command is empty")

    class CodexCliCustodyBackend(CliBackend):
        def __init__(self, base):
            super().__init__(base.name, [*prefix, *argv[1:]], base.model,
                             base.runner, base.timeout)
            self._codex_identity = auth.get("identity", "")

        def health(self) -> bool:
            return True

        def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
            check = (verifier or verify_authenticated_identity)(
                self._codex_identity)
            if check.get("ok") is not True:
                raise BackendError(status_label(check))
            return super().chat(messages, system=system, max_tokens=max_tokens,
                                temperature=temperature, seed=seed)

    return CodexCliCustodyBackend(backend)

def status_label(status: dict) -> str:
    state = status.get("state") or status.get("account_state")
    if state == "authenticated":
        return "ChatGPT account authenticated through Codex app-server"
    if state == "not_authenticated":
        return "ChatGPT account sign-in required"
    if state == "cli_absent":
        return "Codex CLI absent"
    if state == "wrapper_unsupported":
        return "Codex CLI wrapper unsupported"
    if state == "executable_changed":
        return "Codex executable changed before prompt execution"
    if state == "execution_not_ready":
        return "Codex CLI execution not admitted"
    return "Codex app-server account unknown"

__all__ = [
    "JsonlAppServerClient", "app_server_env", "resolve_codex_cli",
    "begin_login", "public_status", "cancel_login", "logout",
    "login_status", "execution_readiness", "authenticated_resolution", "verify_authenticated_identity",
    "bind_authenticated_backend", "status_label",
]
