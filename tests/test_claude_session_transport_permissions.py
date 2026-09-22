import json
import queue
import threading

import pytest

from harness.claude_session_contract import ClaudePermissionDecision
from harness.claude_session_transport import ClaudeSessionTransport, ClaudeSessionTransportError


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

    def readline(self, limit=-1):
        return self._lines.get()


class Outbound:
    def __init__(self):
        self._chunks = []
        self._condition = threading.Condition()

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]


def make_transport():
    incoming, outgoing = Inbound(), Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.2)
    return transport, incoming, outgoing


def test_permission_decision_uses_official_control_response_frame_once():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "type": "control_request",
        "request_id": "req-1",
        "request": {
            "subtype": "can_use_tool",
            "tool_name": "Bash",
            "input": {"command": "git status"},
            "permission_suggestions": None,
            "blocked_path": None,
            "tool_use_id": "tool-1",
        },
    })

    request = transport.pop_control_request(timeout=1.0)
    transport.send_permission_decision(
        request, ClaudePermissionDecision.allow({"command": "git status"}))

    assert outgoing.wait_messages(1) == [{
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "req-1",
            "response": {
                "behavior": "allow",
                "updatedInput": {"command": "git status"},
            },
        },
    }]
    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_permission_decision(
            request, ClaudePermissionDecision.deny("too late"))
    assert caught.value.code == "control_request_resolved"


def test_unknown_control_request_is_fatal_and_gets_error_response():
    transport, incoming, outgoing = make_transport()
    incoming.push({
        "type": "control_request",
        "request_id": "req-2",
        "request": {"subtype": "invented"},
    })

    assert transport.pop_protocol_event(timeout=1.0).kind == "unknown_control_request"
    assert transport.needs_recovery() is True
    assert outgoing.wait_messages(1)[0] == {
        "type": "control_response",
        "response": {
            "subtype": "error",
            "request_id": "req-2",
            "error": "unsupported control request subtype: invented",
        },
    }



