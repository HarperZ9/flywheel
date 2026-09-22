import queue
import threading

import pytest

from harness.codex_provider_session import CodexProviderSessionAdapter
from harness.provider_session_contract import (
    ProviderApprovalDecision,
    ProviderRuntimeBinding,
)

from test_codex_provider_session import (
    Events,
    Server,
    operation,
    request,
    thread_result,
    turn,
)


def test_earlier_terminal_notification_prevents_later_approval_reply():
    server = Server()
    replies = []

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-1")},
        })
        server.incoming.push({
            "id": "approval-late",
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-1", "turnId": "turn-1",
                "itemId": "item-1", "startedAtMs": 1,
            },
        })
        try:
            replies.append(server.outgoing.lines.get(timeout=0.2))
        except queue.Empty:
            pass

    def allow(provider_request):
        return ProviderApprovalDecision.allow(
            provider_request, {"decision": "accept"})

    thread = server.run(script)
    outcome = _adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=allow,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert replies == []


def test_earlier_approval_request_is_answered_before_later_terminal_event():
    server = Server()
    replies = []

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "id": "approval-first",
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-1", "turnId": "turn-1",
                "itemId": "item-1", "startedAtMs": 1,
            },
        })
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-1")},
        })
        replies.append(server.outgoing.read_message())

    def allow(provider_request):
        return ProviderApprovalDecision.allow(
            provider_request, {"decision": "accept"})

    thread = server.run(script)
    outcome = _adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=allow,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert replies == [{
        "id": "approval-first", "result": {"decision": "accept"}}]


def test_identityless_legacy_approval_after_terminal_is_denied_on_next_turn():
    server = Server()
    replies = []
    resume_ready = threading.Event()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-1")},
        })
        assert resume_ready.wait(timeout=1.0)
        resume = server.request("thread/resume")
        assert resume["params"]["threadId"] == "thread-1"
        server.reply(resume, thread_result(turns=[turn("turn-1")]))
        server.reply(server.request("turn/start"), {"turn": turn("turn-2", "inProgress")})
        replies.append(server.outgoing.read_message())
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-2")},
        })

    approvals = []

    def allow(provider_request):
        approvals.append(provider_request)
        return ProviderApprovalDecision.allow(
            provider_request, {"decision": "approved"})

    thread = server.run(script)
    first = _adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=allow,
        cancelled=lambda: False)
    server.incoming.push({
        "id": "stale-legacy-approval",
        "method": "execCommandApproval",
        "params": {"cmd": "echo stale"},
    })
    resume_ready.set()
    second = _adapter_for(server).start_turn(
        request(operation(
            resume_policy="resume_after_reconcile",
            source_operation_ref="op_" + "1" * 32,
            native_thread_id="thread-1"), first.result["provider_session"],
            ref="op_" + "2" * 32),
        emit=Events(), request_approval=allow, cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert first.state == "completed"
    assert second.state == "completed"
    assert replies == [{
        "id": "stale-legacy-approval", "result": {"decision": "denied"}}]
    assert approvals == []


def test_legacy_approval_with_explicit_matching_identity_can_be_allowed():
    server = Server()
    replies = []

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "id": "legacy-approval",
            "method": "execCommandApproval",
            "params": {
                "conversationId": "thread-1", "turnId": "turn-1",
                "cmd": "echo ok",
            },
        })
        replies.append(server.outgoing.read_message())
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-1")},
        })

    def allow(provider_request):
        return ProviderApprovalDecision.allow(
            provider_request, {"decision": "approved"})

    thread = server.run(script)
    outcome = _adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=allow,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert replies == [{
        "id": "legacy-approval", "result": {"decision": "approved"}}]


@pytest.mark.parametrize(
    ("server_sequence", "notification_sequence", "transport_error"),
    [(None, 1, "missing_sequence"), (1, 1, "ambiguous_sequence")],
)
def test_missing_or_ambiguous_cross_queue_sequence_fails_closed(
        server_sequence, notification_sequence, transport_error):
    transport = FakeTransport(server_sequence, notification_sequence)
    client = FakeClient(transport)
    approvals = []
    outcome = _adapter_for_transport(client, transport).start_turn(
        request(operation()), emit=Events(),
        request_approval=lambda approval: approvals.append(approval),
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["transport_error"] == transport_error
    assert outcome.result["side_effect_status"] == "unknown_after_send"
    assert approvals == []
    assert transport.replies == []


class FakeRequest:
    id = "approval-ambiguous"
    method = "item/commandExecution/requestApproval"
    params = {
        "threadId": "thread-1", "turnId": "turn-1",
        "itemId": "item-1", "startedAtMs": 1,
    }

    def __init__(self, sequence):
        if sequence is not None:
            self.sequence = sequence


class FakeNote:
    method = "turn/completed"
    params = {"threadId": "thread-1", "turn": turn("turn-1")}

    def __init__(self, sequence):
        self.sequence = sequence


class FakeTransport:
    def __init__(self, server_sequence, notification_sequence):
        self.server_request = FakeRequest(server_sequence)
        self.notification = FakeNote(notification_sequence)
        self.replies = []

    def pop_server_request(self, *, timeout=0.0):
        value, self.server_request = self.server_request, None
        return value

    def pop_notification(self, *, timeout=0.0):
        value, self.notification = self.notification, None
        return value

    def pop_protocol_event(self, *, timeout=0.0):
        return None

    def reply(self, server_request, *, result=None, error=None):
        self.replies.append((server_request, result, error))


class FakeClient:
    def __init__(self, transport):
        self.transport = transport

    def thread_start(self, **options):
        return thread_result()

    def turn_start(self, thread_id, input_items, **options):
        assert thread_id == "thread-1"
        return {"turn": turn("turn-1", "inProgress")}


def _adapter_for(server):
    return _adapter_for_transport(server.client, server.transport)


def _adapter_for_transport(client, transport):
    return CodexProviderSessionAdapter(
        client_supplier=lambda: client,
        transport_supplier=lambda: transport,
        runtime_binding_supplier=lambda: ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest="cfg-a", capability_digest="cap-a"),
        idle_timeout_s=0.5,
    )
