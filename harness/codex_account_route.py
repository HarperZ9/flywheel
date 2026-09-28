"""Thin route helpers for the Codex consumer-account integration seam."""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from .codex_account_safety import route_payload
from .codex_account_sessions import CodexAccountSessionManager

DEFAULT_MANAGER = CodexAccountSessionManager()


def codex_account_get(
        path: str, query: str = "", *, owner_ref: Any,
        manager: CodexAccountSessionManager = DEFAULT_MANAGER) -> tuple[dict, int]:
    if path == "/api/codex/account":
        return manager.read_status(owner_ref)
    if path == "/api/codex/account/login/result":
        params = parse_qs(query or "", keep_blank_values=True)
        login_id = (params.get("login_id") or params.get("loginId") or [""])[0]
        return manager.login_result(owner_ref, login_id)
    body = route_payload()
    body["state"] = "not_found"
    return body, 404


def codex_account_post(
        path: str, payload: dict | None = None, *, owner_ref: Any,
        manager: CodexAccountSessionManager = DEFAULT_MANAGER,
        visible_ui_action: bool = False) -> tuple[dict, int]:
    payload = payload if isinstance(payload, dict) else {}
    if path == "/api/codex/account/login/start":
        return manager.start_login(
            owner_ref, payload.get("mode"), visible_ui_action=visible_ui_action)
    if path == "/api/codex/account/login/cancel":
        login_id = payload.get("login_id", payload.get("loginId", ""))
        return manager.cancel_login(
            owner_ref, login_id, visible_ui_action=visible_ui_action)
    if path == "/api/codex/account/logout":
        return manager.logout(owner_ref, visible_ui_action=visible_ui_action)
    body = route_payload()
    body["state"] = "not_found"
    return body, 404
