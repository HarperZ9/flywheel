"""Raw managed Codex login response shaping for account routes."""
from __future__ import annotations

from typing import Any

from .codex_account_safety import public_string, trusted_login_url
from .codex_account_state import route_state


def validated_login_start(started: dict, allowed_login_hosts: tuple[str, ...]) -> dict:
    mode = started.get('mode')
    body = route_state('login_started', mode=mode)
    if mode == 'browser':
        body['auth_url'] = trusted_login_url(started.get('auth_url'), allowed_login_hosts)
        return body
    if mode == 'device_code':
        body['verification_url'] = trusted_login_url(
            started.get('verification_url'), allowed_login_hosts)
        body['user_code'] = public_string(started.get('user_code'), limit=80)
        return body
    raise ValueError('login mode invalid')


def start_managed_login_raw(client: Any, *, mode: str) -> dict:
    if mode in {"browser", "chatgpt"}:
        response = client.start_chatgpt_login()
        if response.get("type") != "chatgpt":
            raise ValueError("managed browser login returned the wrong type")
        return {
            "state": "login_started",
            "mode": "browser",
            "login_id": response.get("loginId"),
            "auth_url": response.get("authUrl"),
        }
    if mode in {"device", "device_code", "chatgptDeviceCode"}:
        response = client.start_device_code_login()
        if response.get("type") != "chatgptDeviceCode":
            raise ValueError("managed device-code login returned the wrong type")
        return {
            "state": "login_started",
            "mode": "device_code",
            "login_id": response.get("loginId"),
            "verification_url": response.get("verificationUrl"),
            "user_code": response.get("userCode"),
        }
    raise ValueError("managed Codex login supports browser or device_code only")
