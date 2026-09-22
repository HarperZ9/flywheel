import pytest

from harness.codex_session_client import CodexSessionClient


class RecordingTransport:
    def __init__(self):
        self.calls = []
        self.results = {}

    def request(self, method, params=None, *, timeout=None):
        self.calls.append(("request", method, params, timeout))
        return self.results.get(method, {"ok": method})

    def notify(self, method, params=None):
        self.calls.append(("notify", method, params, None))


def test_initialize_records_response_and_sends_initialized_notification():
    transport = RecordingTransport()
    transport.results["initialize"] = {
        "codexHome": "C:/Users/example/.codex",
        "platformFamily": "windows",
        "platformOs": "windows",
        "userAgent": "codex-cli/0.144.6",
    }
    client = CodexSessionClient(transport)

    assert client.initialize(version="1.2.3") == transport.results["initialize"]

    assert transport.calls == [
        ("request", "initialize", {
            "clientInfo": {
                "name": "flywheel",
                "title": "Flywheel",
                "version": "1.2.3",
            },
            "capabilities": {},
        }, None),
        ("notify", "initialized", None, None),
    ]
    assert client.initialize_response == transport.results["initialize"]


def test_thread_turn_config_and_mcp_methods_use_schema_names():
    transport = RecordingTransport()
    client = CodexSessionClient(transport)

    client.thread_start(cwd="C:/repo", model="gpt-5.5")
    client.thread_resume("thread-1", cwd="C:/repo")
    client.thread_read("thread-1", include_turns=False)
    client.thread_list(limit=5, archived=False)
    client.thread_unsubscribe("thread-1")
    client.turn_start("thread-1", [{"type": "input_text", "text": "hi"}],
                      client_user_message_id="msg-1", model="gpt-5.5")
    client.turn_steer("thread-1", "turn-1",
                      [{"type": "input_text", "text": "steer"}],
                      client_user_message_id="msg-2")
    client.turn_interrupt("thread-1", "turn-1")
    client.model_list(limit=10, include_hidden=True)
    client.config_read(cwd="C:/repo", include_layers=True)
    client.config_requirements_read()
    client.mcp_server_status_list(thread_id="thread-1", detail="tools")
    client.mcp_server_tool_call("thread-1", "server_a", "tool_b",
                                arguments={"x": 1})

    assert [call[:3] for call in transport.calls] == [
        ("request", "thread/start", {"cwd": "C:/repo", "model": "gpt-5.5"}),
        ("request", "thread/resume", {"threadId": "thread-1",
                                       "cwd": "C:/repo"}),
        ("request", "thread/read", {"threadId": "thread-1",
                                     "includeTurns": False}),
        ("request", "thread/list", {"limit": 5, "archived": False}),
        ("request", "thread/unsubscribe", {"threadId": "thread-1"}),
        ("request", "turn/start", {
            "threadId": "thread-1",
            "input": [{"type": "input_text", "text": "hi"}],
            "clientUserMessageId": "msg-1",
            "model": "gpt-5.5",
        }),
        ("request", "turn/steer", {
            "threadId": "thread-1",
            "expectedTurnId": "turn-1",
            "input": [{"type": "input_text", "text": "steer"}],
            "clientUserMessageId": "msg-2",
        }),
        ("request", "turn/interrupt", {"threadId": "thread-1",
                                       "turnId": "turn-1"}),
        ("request", "model/list", {"limit": 10, "includeHidden": True}),
        ("request", "config/read", {"cwd": "C:/repo", "includeLayers": True}),
        ("request", "configRequirements/read", None),
        ("request", "mcpServerStatus/list", {"threadId": "thread-1",
                                              "detail": "tools"}),
        ("request", "mcpServer/tool/call", {
            "threadId": "thread-1",
            "server": "server_a",
            "tool": "tool_b",
            "arguments": {"x": 1},
        }),
    ]


def test_required_native_ids_are_rejected_before_transport_call():
    transport = RecordingTransport()
    client = CodexSessionClient(transport)

    with pytest.raises(ValueError, match="threadId"):
        client.turn_interrupt("", "turn-1")
    with pytest.raises(ValueError, match="turnId"):
        client.turn_interrupt("thread-1", "")

    assert transport.calls == []


def test_bound_params_cannot_be_overridden_through_schema_kwargs():
    transport = RecordingTransport()
    client = CodexSessionClient(transport)

    with pytest.raises(ValueError, match="threadId"):
        client.thread_resume("thread-1", threadId="thread-2")
    with pytest.raises(ValueError, match="threadId"):
        client.turn_start("thread-1", [], threadId="thread-2")
    with pytest.raises(ValueError, match="clientUserMessageId"):
        client.turn_start("thread-1", [], clientUserMessageId="msg-raw")

    assert transport.calls == []
