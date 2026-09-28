"""Small state helpers for Codex account sessions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codex_account_safety import route_payload

LOGIN_COMPLETE = "account/login/completed"
LOGIN_MODES = {"browser", "chatgpt", "device", "device_code", "chatgptDeviceCode"}

@dataclass
class Session:
    owner_ref: str
    login_id: str
    mode: str
    client: Any
    expires_at: float
    reserved: bool = False


def route_state(state: str, **extra: Any) -> dict:
    body = route_payload()
    body.update({"state": state, **extra})
    return body


def rejected_response() -> tuple[dict, int]:
    return route_state("rejected", reason="visible UI action required"), 403


def unknown_login_response() -> tuple[dict, int]:
    return route_state("unknown_login", reason="unknown login handle"), 404


def bad_request_response(reason: str) -> tuple[dict, int]:
    return route_state("bad_request", reason=reason), 400


def notification_overflowed(client: Any) -> bool:
    overflowed = getattr(client, "notification_overflowed", None)
    return bool(overflowed()) if overflowed else False


def completion_for(session: Session, notification: Any) -> dict | None:
    if not isinstance(notification, dict):
        return None
    if notification.get("method") != LOGIN_COMPLETE:
        return None
    params = notification.get("params")
    if not isinstance(params, dict) or params.get("loginId") != session.login_id:
        return None
    return params
