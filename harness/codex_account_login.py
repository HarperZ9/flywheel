"""Raw managed Codex login response shaping for account routes."""
from __future__ import annotations

from typing import Any


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
