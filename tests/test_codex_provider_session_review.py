import queue

import pytest

from harness.provider_session_contract import (
    ProviderApprovalDecision,
    ProviderOperationRequest,
)

from test_codex_provider_session import (
    JOURNEY,
    OWNER,
    Events,
    Server,
    adapter_for,
    operation,
    request,
    thread_result,
    turn,
)


def source_session():
    return {
        "provider": "codex",
        "native_session_id": "session-1",
        "native_thread_id": "thread-1",
        "native_turn_id": "turn-1",
        "last_provider_event_id": "event-1",
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
    }


def test_resume_turn_rejects_wrong_thread_response_before_starting_work():
    server = Server()
    observed = []

    def script(server):
        server.reply(server.request("thread/resume"), thread_result(thread_id="wrong-thread"))
        try:
            observed.append(server.outgoing.lines.get(timeout=0.2))
        except queue.Empty:
            pass

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation(
            resume_policy="resume_after_reconcile",
            source_operation_ref="op_" + "1" * 32,
            native_thread_id="thread-1"), source_session(), ref="op_" + "2" * 32),
        emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert observed == []


def test_terminal_event_for_wrong_thread_is_not_accepted():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.notify("turn/completed", {
            "threadId": "wrong-thread", "turn": turn("turn-1")})
        server.incoming.eof()

    thread = server.run(script)
    events = Events()
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=events, request_approval=lambda r: None,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "indeterminate"
    assert any(e["phase"] == "ignored_native_event" for e in events.events)


def test_terminal_event_missing_thread_id_is_not_accepted():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.notify("turn/completed", {"turn": turn("turn-1")})
        server.incoming.eof()

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "indeterminate"


@pytest.mark.parametrize("bad_params", [
    {"threadId": "wrong-thread", "turnId": "turn-1"},
    {"threadId": "thread-1", "turnId": "wrong-turn"},
])
def test_wrong_thread_or_turn_approval_is_denied_even_when_resolver_allows(
        bad_params):
    server = Server()
    replies = []

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {
                **bad_params,
                "itemId": "item-1", "startedAtMs": 1,
            },
        })
        replies.append(server.outgoing.read_message())
        server.incoming.push({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": turn("turn-1")},
        })

    def allow(request):
        return ProviderApprovalDecision.allow(request, {"decision": "accept"})

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=allow,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert replies == [{"id": "approval-1", "result": {"decision": "decline"}}]


def test_turn_start_transport_error_after_write_is_ambiguous():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        start = server.request("turn/start")
        server.incoming.push({"id": start["id"], "error": {"code": -32603, "message": "boom"}})

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["side_effect_status"] == "unknown_after_send"
    assert outcome.result["transport_error"] == "peer_error"


def test_cancel_interrupt_transport_error_after_write_is_ambiguous():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        interrupt = server.request("turn/interrupt")
        server.incoming.push({"id": interrupt["id"], "error": {"code": -32603, "message": "boom"}})

    thread = server.run(script)
    checks = iter([True, True])
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: next(checks))
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["side_effect_status"] == "unknown_after_send"
    assert outcome.result["transport_error"] == "peer_error"


def test_resume_with_missing_turns_is_not_complete_history():
    server = Server()

    def script(server):
        server.reply(server.request("thread/resume"), thread_result())
        read = server.request("thread/read")
        response = thread_result()
        del response["thread"]["turns"]
        server.reply(read, response)

    thread = server.run(script)
    req = ProviderOperationRequest(
        OWNER, JOURNEY, "op_" + "3" * 32, "provider.session.resume",
        {
            "provider": "codex",
            "source_operation_ref": "op_" + "1" * 32,
            "workspace_ref": "workspace-a",
            "config_digest": "cfg-a",
            "capability_digest": "cap-a",
            "native_thread_id": "thread-1",
            "native_turn_id": "turn-1",
            "history_limit": 20,
            "stream": True,
        },
        source_session(),
    )
    outcome = adapter_for(server).resume(req, emit=Events())
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "missing"


def test_reconcile_reports_structured_terminal_observation():
    server = Server()

    def script(server):
        read = server.request("thread/read")
        assert read["params"] == {"threadId": "thread-1", "includeTurns": True}
        server.reply(read, thread_result(turns=[turn("turn-1")]))

    target_ref = "op_" + "1" * 32
    thread = server.run(script)
    req = ProviderOperationRequest(
        OWNER, JOURNEY, "op_" + "4" * 32, "provider.session.reconcile",
        {
            "provider": "codex",
            "target_operation_ref": target_ref,
            "workspace_ref": "workspace-a",
            "config_digest": "cfg-a",
            "capability_digest": "cap-a",
            "native_thread_id": "thread-1",
            "native_turn_id": "turn-1",
            "history_limit": 20,
            "stream": True,
        },
        source_session(),
    )
    outcome = adapter_for(server).reconcile(req, emit=Events())
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert outcome.result["side_effect_status"] == "native_terminal_observed"
    assert outcome.result["provider_observation"] == {
        **source_session(),
        "target_operation_ref": target_ref,
        "observed_status": "native_terminal_observed",
    }
