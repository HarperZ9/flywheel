"""Short-lived app-server sessions for browser/device-code login."""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_SESSIONS: dict[str, "LoginSession"] = {}


class LoginSession:
    def __init__(self, *, provider: str, mode: str, login_id: str, client,
                 started: float | None = None):
        self.provider = provider
        self.mode = mode
        self.login_id = login_id
        self.client = client
        self.started = started or time.time()

    def close(self) -> None:
        self.client.close()

    def cancel(self) -> dict:
        try:
            result = self.client.request("account/login/cancel", {"loginId": self.login_id})
        finally:
            self.close()
            forget(self.login_id)
        state = result.get("status", "unknown")
        return {"ok": state == "canceled", "provider": self.provider, "state": state}

    def status(self) -> dict:
        for msg in list(self.client.notifications):
            if msg.get("method") != "account/login/completed":
                continue
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            if params.get("loginId") not in ("", None, self.login_id):
                continue
            if params.get("success") is not True:
                self.close(); forget(self.login_id)
                return {"ok": False, "provider": self.provider, "state": "failed"}
            result = self.client.request("account/read", {"refreshToken": False})
            account = result.get("account") if isinstance(result, dict) else {}
            ok = isinstance(account, dict) and account.get("type") == "chatgpt"
            ok = ok and result.get("requiresOpenaiAuth") is False
            self.close(); forget(self.login_id)
            return {"ok": ok, "provider": self.provider,
                    "state": "done" if ok else "failed"}
        return {"ok": True, "provider": self.provider, "state": "running"}


def remember(session: LoginSession) -> None:
    with _LOCK:
        _SESSIONS[session.login_id] = session


def get(login_id: str) -> LoginSession | None:
    with _LOCK:
        return _SESSIONS.get(login_id)


def forget(login_id: str) -> None:
    with _LOCK:
        _SESSIONS.pop(login_id, None)


def close_provider(provider: str) -> None:
    with _LOCK:
        sessions = [s for s in _SESSIONS.values() if s.provider == provider]
    for session in sessions:
        session.close()
        forget(session.login_id)
