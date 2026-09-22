import json
import queue

from harness.claude_session_transport import ClaudeSessionTransport
from harness.provider_session_contract import ProviderApprovalDecision

from test_claude_provider_session_support import (
    Events,
    FakeClient,
    adapter_for,
    operation,
    permission_request,
    request,
    result_event,
    tool_use_event,
)


class InjectedSurfaceWithoutCustody:
    def __init__(self):
        self.sent = []
        self.decisions = []

    def send_text(self, text):
        self.sent.append(("text", text))

    def next_event(self, timeout=None):
        return result_event()

    def next_control_request(self, timeout=None):
        return None

    def next_protocol_event(self, timeout=None):
        return None

    def send_permission_decision(self, request, decision):
        self.decisions.append((request, decision))


class TransportClient:
    def __init__(self, transport):
        self.transport = transport

    def send_text(self, text):
        self.transport.send_user_message(text)

    def next_event(self, timeout=None):
        return self.transport.pop_event(timeout=timeout)

    def next_control_request(self, timeout=None):
        return self.transport.pop_control_request(timeout=timeout)

    def next_protocol_event(self, timeout=None):
        return self.transport.pop_protocol_event(timeout=timeout)

    def send_permission_decision(self, request, decision):
        self.transport.send_permission_decision(request, decision)

    def has_pending_control_requests(self):
        return self.transport.has_pending_control_requests()

    def mark_recovery_needed(self):
        self.transport.mark_recovery_needed()

    def interrupt(self, timeout=None):
        return self.transport.interrupt(timeout=timeout)


def test_claude_adapter_requires_control_custody_surface_before_input():
    client = InjectedSurfaceWithoutCustody()

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_PROTOCOL_ERROR"
    assert outcome.result["side_effect_status"] == "none"
    assert outcome.result["surface_error"] == "missing_control_custody_surface"
    assert client.sent == []


class LateControlAfterCompletedTurn:
    def __init__(self):
        self._lines = queue.Queue()
        self._messages = []
        self._user_writes = 0

    def write(self, chunk):
        message = json.loads(chunk.decode("utf-8"))
        self._messages.append(message)
        if message.get("type") != "user":
            return len(chunk)
        self._user_writes += 1
        if self._user_writes == 1:
            self._push({
                "type": "result", "subtype": "success", "duration_ms": 1,
                "duration_api_ms": 1, "is_error": False, "num_turns": 1,
                "session_id": "claude-session-1",
            })
        elif self._user_writes == 2:
            self._push({
                "type": "assistant", "session_id": "claude-session-1",
                "message": {"role": "assistant", "content": [{
                    "type": "tool_use", "id": "tool-old",
                    "name": "Bash", "input": {"command": "pwd"},
                }]},
            })
            self._push({
                "type": "control_request", "request_id": "req-late",
                "request": {
                    "subtype": "can_use_tool", "tool_name": "Bash",
                    "input": {"command": "pwd"}, "tool_use_id": "tool-old",
                },
            })
        return len(chunk)

    def flush(self):
        pass

    def _push(self, message):
        self._lines.put(json.dumps(message, separators=(",", ":")).encode() + b"\n")

    def readline(self, limit=-1):
        return self._lines.get()

    def messages(self):
        return list(self._messages)


def test_completed_transport_is_not_reused_for_fresh_thread_input():
    incoming = LateControlAfterCompletedTurn()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=incoming, default_timeout=0.05)
    client = TransportClient(transport)
    adapter = adapter_for(client, transport_supplier=lambda: transport)
    approvals = []

    first = adapter.start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    second = adapter.start_turn(
        request(operation(client_user_message_id="msg-2")), emit=Events(),
        request_approval=lambda r: approvals.append(r) or ProviderApprovalDecision.allow(
            r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert first.state == "completed"
    assert approvals == []
    assert second.state == "failed"
    assert second.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert second.result["transport_error"] == "stale_transport_session"
    assert second.result["side_effect_status"] == "none"
    users = [m for m in incoming.messages() if m["type"] == "user"]
    responses = [m for m in incoming.messages() if m["type"] == "control_response"]
    assert len(users) == 1
    assert responses == []
    assert transport.needs_recovery()


def test_permission_is_allowed_when_bound_to_same_turn_tool_use():
    control = permission_request(tool_use_id="tool-current")
    client = FakeClient(events=[
        tool_use_event("tool-current", sequence=1),
        result_event(sequence=2),
    ], controls=[control])

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda r: ProviderApprovalDecision.allow(r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert client.decisions[0][0] == control
    assert client.decisions[0][1].behavior == "allow"


class ControlBeforeToolUseStdout(FakeClient):
    def __init__(self):
        super().__init__()
        self.step = 0
        self.control = permission_request(tool_use_id="tool-before")

    def next_event(self, timeout=None):
        if self.step == 1:
            self.step = 2
            return result_event(sequence=2)
        return None

    def next_control_request(self, timeout=None):
        if self.step == 0:
            self.step = 1
            self.pending_controls += 1
            return self.control
        return None


def test_permission_can_arrive_before_tool_use_stdout_event():
    client = ControlBeforeToolUseStdout()

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda r: ProviderApprovalDecision.allow(
            r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert client.decisions[0][0] == client.control
    assert client.decisions[0][1].behavior == "allow"


class DuplicateToolUseControlSurface(FakeClient):
    def __init__(self):
        super().__init__()
        self.step = 0
        self.first = permission_request(
            tool_use_id="tool-dup", request_id="req-dup-1")
        self.second = permission_request(
            tool_use_id="tool-dup", request_id="req-dup-2")

    def next_event(self, timeout=None):
        if self.step == 0:
            self.step = 1
            return tool_use_event("tool-dup", sequence=1)
        if self.step == 3:
            self.step = 4
            return result_event(sequence=2)
        return None

    def next_control_request(self, timeout=None):
        if self.step == 1:
            self.step = 2
            self.pending_controls += 1
            return self.first
        if self.step == 2:
            self.step = 3
            self.pending_controls += 1
            return self.second
        return None


def test_duplicate_tool_use_id_is_denied_after_first_reply():
    client = DuplicateToolUseControlSurface()
    approvals = []

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda r: approvals.append(r) or ProviderApprovalDecision.allow(
            r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["transport_error"] == "duplicate_tool_use_id"
    assert len(approvals) == 1
    assert [decision.behavior for _, decision in client.decisions] == ["allow", "deny"]
    assert client.recovery_needed
