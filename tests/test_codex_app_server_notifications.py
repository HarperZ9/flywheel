import io
import json

from harness.codex_app_server_client import CodexAppServerStdioTransport


def test_stdio_transport_preserves_login_completion_notification_for_correlation():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps({"method": "account/login/completed",
                            "params": {"loginId": "login-1",
                                       "success": True, "error": None}}) + "\n" +
                json.dumps({"id": 1, "result": {"type": "chatgpt",
                                                "loginId": "login-1",
                                                "authUrl": "https://auth.openai.com"}}) + "\n"
            )

        def poll(self):
            return None

    transport = CodexAppServerStdioTransport(process=FakeProcess(), timeout=1.0)

    result = transport.request("account/login/start", {"type": "chatgpt"})
    assert result["loginId"] == "login-1"
    assert transport.pop_notification(timeout=1.0) == {
        "method": "account/login/completed",
        "params": {"loginId": "login-1", "success": True, "error": None},
    }


def test_stdio_transport_exposes_notification_arriving_after_response():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps({"id": 1, "result": {"ok": True}}) + "\n" +
                json.dumps({"method": "account/login/completed",
                            "params": {"loginId": "login-1",
                                       "success": True, "error": None}}) + "\n"
            )

        def poll(self):
            return None

    transport = CodexAppServerStdioTransport(process=FakeProcess(), timeout=1.0)

    assert transport.request("account/login/start", {"type": "chatgpt"}) == {"ok": True}
    assert transport.pop_notification(timeout=1.0) == {
        "method": "account/login/completed",
        "params": {"loginId": "login-1", "success": True, "error": None},
    }


def test_stdio_transport_filters_unrelated_notifications_under_flood():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            unrelated = "".join(
                json.dumps({"method": f"thread/noise/{i}", "params": {}}) + "\n"
                for i in range(100)
            )
            self.stdout = io.StringIO(
                unrelated +
                json.dumps({"id": 1, "result": {"ok": True}}) + "\n" +
                json.dumps({"method": "account/login/completed",
                            "params": {"loginId": "login-1",
                                       "success": True, "error": None}}) + "\n"
            )

        def poll(self):
            return None

    transport = CodexAppServerStdioTransport(
        process=FakeProcess(), timeout=1.0, notification_queue_size=2)

    assert transport.request("account/read", {}) == {"ok": True}
    assert transport.pop_notification(timeout=1.0)["params"]["loginId"] == "login-1"
    assert transport.pop_notification(timeout=0.0) is None
    assert transport.notification_overflowed() is False


def test_stdio_transport_reports_completion_notification_overflow():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps({"method": "account/login/completed",
                            "params": {"loginId": "other-1",
                                       "success": True, "error": None}}) + "\n" +
                json.dumps({"method": "account/login/completed",
                            "params": {"loginId": "other-2",
                                       "success": True, "error": None}}) + "\n" +
                json.dumps({"id": 1, "result": {"ok": True}}) + "\n"
            )

        def poll(self):
            return None

    transport = CodexAppServerStdioTransport(
        process=FakeProcess(), timeout=1.0, notification_queue_size=1)

    assert transport.request("account/read", {}) == {"ok": True}
    assert transport.pop_notification(timeout=1.0)["params"]["loginId"] == "other-1"
    assert transport.notification_overflowed() is True
