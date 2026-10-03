"""Managed Codex account binding and login-completion hook types."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .codex_account_safety import safe_error
from .codex_account_state import route_state


@dataclass(frozen=True)
class ManagedCodexAccountBinding:
    client: Any
    profile: Any
    inventory: Any
    executable: Path
    executable_sha256: str
    codex_version: str
    policy_root: Path


@dataclass(frozen=True)
class LoginCompletionContext:
    owner_ref: str
    login_id: str
    mode: str
    completed: dict
    binding: ManagedCodexAccountBinding


def account_client(value: Any) -> Any:
    return value.client if isinstance(value, ManagedCodexAccountBinding) else value


def account_binding(value: Any) -> ManagedCodexAccountBinding | None:
    return value if isinstance(value, ManagedCodexAccountBinding) else None


def close_account_client(value: Any) -> bool:
    binding = isinstance(value, ManagedCodexAccountBinding)
    client = account_client(value)
    close = getattr(client, 'close', None)
    if close is None:
        return not binding
    try:
        result = close()
    except Exception:
        return False
    if binding:
        if result is True:
            return True
        try:
            from .codex_managed_account_client import ManagedCodexAccountClient
        except Exception:
            return False
        return isinstance(client, ManagedCodexAccountClient) and result is None
    return result is not False


def successful_login_response(session: Any, login: str, completed: dict, cleanup_ok: bool,
                              hook: Callable[[LoginCompletionContext], Any] | None):
    base = {'login_id': login, 'completion_state': 'completed', 'mode': session.mode}
    if not cleanup_ok:
        return route_state('authenticated_restart_held', **base,
                           reason='managed cleanup incomplete'), 200
    binding = account_binding(session.client)
    if hook is None:
        return route_state('authenticated', **base), 200
    if binding is None:
        return route_state('authenticated_restart_held', **base,
                           reason='managed account binding unavailable'), 200
    try:
        recorded = hook(LoginCompletionContext(session.owner_ref, login, session.mode, dict(completed), binding))
        from .codex_managed_profile_manifest import CodexProfileInventoryRef
        if not isinstance(recorded, CodexProfileInventoryRef):
            raise RuntimeError('auth inventory extension was not recorded')
    except Exception as exc:
        return route_state('authenticated_restart_held', **base, reason=safe_error(exc)), 200
    return route_state('authenticated', **base,
                       restart_persistence='auth_extension_recorded',
                       inventory_sha256=recorded.sha256), 200
