from __future__ import annotations

from harness.codex_account_sessions import CodexAccountSessionManager


OWNER = "owner_" + "a" * 32


def test_account_manager_shutdown_retains_unclosed_pending_client(tmp_path):
    class UnclosedClient:
        def __init__(self):
            self.close_calls = 0

        def start_chatgpt_login(self):
            return {
                "type": "chatgpt",
                "loginId": "login-browser-1",
                "authUrl": "https://auth.openai.com/login/login-browser-1",
            }

        def close(self):
            self.close_calls += 1
            return False

        def pop_notification(self, *, timeout=0.0):
            return None

        def notification_overflowed(self):
            return False

    client = UnclosedClient()
    manager = CodexAccountSessionManager(client_factory=lambda: client)
    started, started_status = manager.start_login(
        OWNER, "browser", visible_ui_action=True)

    cleanup_ok = manager.shutdown()
    pending, pending_status = manager.login_result(OWNER, started["login_id"])

    assert started_status == 202
    assert cleanup_ok is False
    assert client.close_calls == 1
    assert pending_status == 202
    assert pending["state"] == "pending"
