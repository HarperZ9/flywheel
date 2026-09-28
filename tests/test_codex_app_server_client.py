import io
import json
import subprocess

import pytest

from harness.codex_app_server_client import (
    CodexAppServerClient,
    CodexAppServerError,
    CodexAppServerStdioTransport,
)


class RecordingTransport:
    def __init__(self, *results):
        self.calls = []
        self.results = list(results)

    def request(self, method, params=None):
        self.calls.append((method, params))
        return self.results.pop(0)


def test_client_uses_generated_app_server_methods_and_params():
    transport = RecordingTransport(
        {"account": None, "requiresOpenaiAuth": True},
        {"type": "chatgpt", "loginId": "L1", "authUrl": "https://auth.test"},
        {"type": "chatgptDeviceCode", "loginId": "L2",
         "verificationUrl": "https://verify.test", "userCode": "ABCD"},
        {"status": "cancelled"},
        {},
        {"data": [], "nextCursor": None},
        {"namespaceTools": True, "imageGeneration": False, "webSearch": True},
    )
    client = CodexAppServerClient(transport)

    assert client.get_account(refresh_token=True)["requiresOpenaiAuth"] is True
    assert client.start_chatgpt_login()["authUrl"] == "https://auth.test"
    assert client.start_device_code_login()["userCode"] == "ABCD"
    assert client.cancel_login("L1")["status"] == "cancelled"
    assert client.logout() == {}
    assert client.list_models(cursor="c1", limit=2, include_hidden=True)["data"] == []
    assert client.read_model_provider_capabilities()["webSearch"] is True

    assert transport.calls == [
        ("account/read", {"refreshToken": True}),
        ("account/login/start", {"type": "chatgpt"}),
        ("account/login/start", {"type": "chatgptDeviceCode"}),
        ("account/login/cancel", {"loginId": "L1"}),
        ("account/logout", None),
        ("model/list", {"cursor": "c1", "limit": 2, "includeHidden": True}),
        ("modelProvider/capabilities/read", {}),
    ]


def test_stdio_transport_writes_jsonrpc_and_reads_matching_result():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps({"method": "account/updated", "params": {}}) + "\n" +
                json.dumps({"id": 1, "result": {"ok": True}}) + "\n"
            )

        def poll(self):
            return None

        def terminate(self):
            pass

    proc = FakeProcess()
    transport = CodexAppServerStdioTransport(process=proc, timeout=1.0)

    assert transport.request("account/read", {"refreshToken": False}) == {"ok": True}
    assert json.loads(proc.stdin.getvalue().strip()) == {
        "id": 1,
        "method": "account/read",
        "params": {"refreshToken": False},
    }


def test_stdio_transport_error_does_not_echo_secret_text():
    class FakeProcess:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(json.dumps({
                "id": 1,
                "error": {"code": 400, "message": "bad sk-SECRET"},
            }) + "\n")

        def poll(self):
            return None

    transport = CodexAppServerStdioTransport(process=FakeProcess(), timeout=1.0)

    with pytest.raises(CodexAppServerError) as failure:
        transport.request("model/list", {})

    assert "model/list failed" in str(failure.value)
    assert "SECRET" not in str(failure.value)


class CleanupProcess:
    def __init__(self, stdout_text, *, wait_timeout=False):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(stdout_text)
        self.wait_timeout = wait_timeout
        self.terminated = False
        self.waited = 0
        self.killed = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited += 1
        if self.wait_timeout and not self.killed:
            raise subprocess.TimeoutExpired(["codex"], timeout)
        return 0

    def kill(self):
        self.killed = True


def test_connect_closes_transport_if_initialize_fails():
    proc = CleanupProcess(json.dumps({
        "id": 1,
        "error": {"code": 500, "message": "bad sk-SECRET"},
    }) + "\n")

    with pytest.raises(CodexAppServerError) as failure:
        CodexAppServerClient.connect(process=proc, timeout=1.0)

    assert "SECRET" not in str(failure.value)
    assert proc.stdin.closed
    assert proc.terminated is True
    assert proc.waited == 1
    assert proc.killed is False


def test_stdio_transport_close_kills_after_bounded_terminate_timeout():
    proc = CleanupProcess("", wait_timeout=True)
    transport = CodexAppServerStdioTransport(process=proc, timeout=1.0)

    transport.close()

    assert proc.stdin.closed
    assert proc.terminated is True
    assert proc.killed is True
    assert proc.waited == 2
