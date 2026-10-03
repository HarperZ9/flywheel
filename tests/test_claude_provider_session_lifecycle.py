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
)


class TransportClient:
    def __init__(self, transport):
        self.transport = transport

    def send_text(self, text):
        self.transport.send_user_message(text)

    def send_blocks(self, blocks):
        self.transport.send_user_message(blocks)

    def next_event(self, timeout=None):
        return self.transport.pop_event(timeout=timeout)

    def next_control_request(self, timeout=None):
        return self.transport.pop_control_request(timeout=timeout)

    def next_protocol_event(self, timeout=None):
        return self.transport.pop_protocol_event(timeout=timeout)

    def send_permission_decision(self, request, decision):
        return self.transport.send_permission_decision(request, decision)

    def has_pending_control_requests(self):
        return self.transport.has_pending_control_requests()

    def mark_recovery_needed(self):
        return self.transport.mark_recovery_needed()

    def interrupt(self, timeout=None):
        return self.transport.interrupt(timeout=timeout)


def allow(req):
    return ProviderApprovalDecision.allow(req, {"command": "pwd"})


def test_no_session_event_bound_spends_surface_before_next_input():
    client = FakeClient()
    adapter = adapter_for(client)

    first = adapter.start_turn(
        request(operation(timeout_s=0)), emit=Events(),
        request_approval=allow, cancelled=lambda: False)
    client.controls.append(permission_request(
        tool_use_id="arbitrary-after-timeout", request_id="req-old"))
    client.events.append(result_event(sequence=2))
    second = adapter.start_turn(
        request(operation(client_user_message_id="msg-2")), emit=Events(),
        request_approval=allow, cancelled=lambda: False)

    assert first.state == "failed"
    assert first.result["transport_error"] == "event_bound_exceeded"
    assert first.result["side_effect_status"] == "unknown_after_send"
    assert second.state == "failed"
    assert second.result["transport_error"] == "stale_transport_session"
    assert second.result["side_effect_status"] == "none"
    assert client.sent == [("text", "hello")]
    assert client.decisions == []
    assert client.recovery_needed


def test_acknowledged_cancel_spends_surface_before_next_input():
    client = FakeClient()
    checks = iter([False, True, True])
    adapter = adapter_for(client)

    first = adapter.start_turn(
        request(operation()), emit=Events(),
        request_approval=allow, cancelled=lambda: next(checks))
    client.controls.append(permission_request(
        tool_use_id="arbitrary-after-cancel", request_id="req-cancel"))
    client.events.append(result_event(sequence=2))
    second = adapter.start_turn(
        request(operation(client_user_message_id="msg-2")), emit=Events(),
        request_approval=allow, cancelled=lambda: False)

    assert first.state == "failed"
    assert first.result["reason"] == "AGENT_NATIVE_CANCELLED"
    assert first.result["cancellation_status"] == "acknowledged"
    assert second.state == "failed"
    assert second.result["transport_error"] == "stale_transport_session"
    assert second.result["side_effect_status"] == "none"
    assert client.sent == [("text", "hello")]
    assert client.decisions == []
    assert client.interrupt_calls == 1
    assert client.recovery_needed


class BlockingInbound:
    def __init__(self):
        self.lines = queue.Queue()

    def readline(self, limit=-1):
        return self.lines.get()

    def close(self):
        self.lines.put(b"")


class Outbound:
    def __init__(self):
        self.chunks = []

    def write(self, chunk):
        self.chunks.append(bytes(chunk))
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        pass

    def messages(self):
        return [json.loads(chunk.decode("utf-8")) for chunk in self.chunks]


def test_actual_transport_timeout_marks_recovery_and_blocks_reuse_before_input():
    incoming = BlockingInbound()
    outgoing = Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.01)
    client = TransportClient(transport)
    adapter = adapter_for(client, transport_supplier=lambda: transport)
    try:
        first = adapter.start_turn(
            request(operation(timeout_s=0)), emit=Events(),
            request_approval=allow, cancelled=lambda: False)
        second = adapter.start_turn(
            request(operation(client_user_message_id="msg-2")), emit=Events(),
            request_approval=allow, cancelled=lambda: False)
        assert first.state == "failed"
        assert first.result["transport_error"] == "timeout"
        assert second.state == "failed"
        assert second.result["transport_error"] == "stale_transport_session"
        assert second.result["side_effect_status"] == "none"
        assert len([m for m in outgoing.messages() if m["type"] == "user"]) == 1
        assert transport.needs_recovery()
    finally:
        transport.shutdown(timeout=0.05)


def test_prewrite_turn_in_flight_reports_no_new_input_sent_and_recovery():
    incoming = BlockingInbound()
    outgoing = Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.01)
    client = TransportClient(transport)
    adapter = adapter_for(client, transport_supplier=lambda: transport)
    try:
        transport.send_user_message("external in-flight")
        outcome = adapter.start_turn(
            request(operation()), emit=Events(),
            request_approval=allow, cancelled=lambda: False)
        assert outcome.state == "failed"
        assert outcome.result["transport_error"] == "turn_in_flight"
        assert outcome.result["side_effect_status"] == "none"
        assert len([m for m in outgoing.messages() if m["type"] == "user"]) == 1
        assert transport.needs_recovery()
    finally:
        transport.shutdown(timeout=0.05)
