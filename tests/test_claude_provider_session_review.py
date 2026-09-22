import json
import queue
import threading

from harness.claude_session_contract import ClaudeSessionEvent
from harness.claude_session_transport import (
    ClaudeSessionTransport,
    ClaudeSessionTransportError,
)
from harness.provider_session_contract import ProviderApprovalDecision

from test_claude_provider_session_support import (
    Events,
    FakeClient,
    SendOnlyClient,
    SurfaceAfterSession,
    adapter_for,
    assistant_event,
    operation,
    permission_request,
    request,
    result_event,
)


def test_claude_adapter_requires_observation_surface_before_input():
    client = SendOnlyClient()

    outcome = adapter_for(client, transport_supplier=lambda: None).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert client.sent == []
    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_PROTOCOL_ERROR"
    assert outcome.result["side_effect_status"] == "none"


def test_claude_adapter_preserves_side_effect_uncertainty_after_read_error():
    error = ClaudeSessionTransportError("read_error", "event stream failed")
    client = FakeClient(event_error=error)

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert client.sent == [("text", "hello")]
    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["side_effect_status"] == "unknown_after_send"


def test_claude_adapter_rejects_malformed_result_without_completing():
    event = ClaudeSessionEvent(1, "result", {
        "type": "result", "subtype": "success",
        "session_id": "claude-session-1",
    }, "claude-session-1")

    outcome = adapter_for(FakeClient(events=[event])).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["transport_error"] == "malformed_result"


def test_claude_adapter_rejects_session_change_after_prior_event():
    client = FakeClient(events=[
        assistant_event("session-a", sequence=1),
        result_event("session-b", sequence=2),
    ])

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert outcome.result["side_effect_status"] == "input_sent"
    assert outcome.result["observed_native_session_id"] == "session-b"


def test_claude_adapter_consumes_terminal_result_before_queued_permission():
    control = permission_request()
    client = FakeClient(events=[result_event("session-a")], controls=[control])

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda r: ProviderApprovalDecision.allow(r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert client.decisions == []


def test_claude_adapter_binds_approval_identity_to_observed_session():
    client = SurfaceAfterSession()
    observed = []

    def deny(approval):
        observed.append(approval)
        return ProviderApprovalDecision.deny(approval, "no")

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=deny,
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert observed[0].native_session_id == "claude-session-1"


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

    def readline(self, limit=-1):
        return self._lines.get()


class TriggerOutbound:
    def __init__(self, incoming):
        self.incoming = incoming
        self._chunks = []
        self._condition = threading.Condition()
        self._triggered = False

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            if not self._triggered:
                self._triggered = True
                self.incoming.push({
                    "type": "control_request",
                    "request_id": "req-early",
                    "request": {
                        "subtype": "can_use_tool", "tool_name": "Bash",
                        "input": {"command": "pwd"}, "tool_use_id": "tool-early",
                    },
                })
                self.incoming.push({
                    "type": "result", "subtype": "success", "duration_ms": 1,
                    "duration_api_ms": 1, "is_error": False, "num_turns": 1,
                    "session_id": "claude-session-1",
                })
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def messages(self):
        with self._condition:
            return [json.loads(chunk.decode("utf-8")) for chunk in self._chunks]


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


def test_real_transport_unresolved_control_cannot_leak_into_next_turn():
    incoming = Inbound()
    outgoing = TriggerOutbound(incoming)
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    client = TransportClient(transport)
    adapter = adapter_for(client, transport_supplier=lambda: transport)

    first = adapter.start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda r: ProviderApprovalDecision.allow(r, {"command": "pwd"}),
        cancelled=lambda: False)
    second = adapter.start_turn(
        request(operation(client_user_message_id="msg-2")), emit=Events(),
        request_approval=lambda r: ProviderApprovalDecision.allow(r, {"command": "pwd"}),
        cancelled=lambda: False)

    assert first.state == "failed"
    assert first.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert first.result["transport_error"] == "pending_control_request"
    assert second.state == "failed"
    assert second.result["side_effect_status"] == "none"
    assert [message["type"] for message in outgoing.messages()] == ["user"]
