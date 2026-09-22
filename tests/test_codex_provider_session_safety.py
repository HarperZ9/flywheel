from harness.codex_provider_session import CodexProviderSessionAdapter
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
    finish_turn,
    operation,
    request,
    thread_result,
    turn,
)


def test_codex_adapter_denies_stale_approval_and_errors_unknown_request():
    server = Server()
    observed = []

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.push({
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-1", "turnId": "turn-1",
                "itemId": "item-1", "startedAtMs": 1,
            },
        })
        stale = server.outgoing.read_message()
        observed.append(stale)
        server.incoming.push({
            "id": "attest-1",
            "method": "attestation/generate",
            "params": {"challenge": "opaque"},
        })
        unknown = server.outgoing.read_message()
        observed.append(unknown)
        finish_turn(server, "turn-1")

    def stale_allow(provider_request):
        return ProviderApprovalDecision(
            "allow", "wrong-identity", "",
            {"decision": "accept"})

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=stale_allow,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "completed"
    assert observed[0]["id"] == "approval-1"
    assert observed[0]["result"] == {"decision": "decline"}
    assert observed[1]["id"] == "attest-1"
    assert observed[1]["error"]["code"] == -32603


def test_codex_adapter_marks_eof_after_input_as_ambiguous():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        server.incoming.eof()

    thread = server.run(script)
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "indeterminate"
    assert outcome.result["side_effect_status"] == "unknown_after_send"
    assert outcome.result["transport_error"] == "eof"


def test_codex_adapter_rejects_cross_owner_source_before_provider_input():
    server = Server()
    source = {
        "provider": "codex",
        "native_session_id": "session-1",
        "native_thread_id": "thread-1",
        "native_turn_id": "turn-1",
        "owner_ref": "owner_" + "b" * 32,
        "journey_ref": JOURNEY,
        "operation_ref": "op_" + "1" * 32,
    }
    req = ProviderOperationRequest(
        OWNER, JOURNEY, "op_" + "2" * 32, "provider.session.turn",
        operation(
            resume_policy="resume_after_reconcile",
            source_operation_ref="op_" + "1" * 32,
            native_thread_id="thread-1"),
        source,
    )

    outcome = adapter_for(server).start_turn(
        req, emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert server.outgoing.lines.empty()


def test_codex_adapter_reconcile_fails_when_native_history_is_missing():
    server = Server()

    def script(server):
        read = server.request("thread/read")
        assert read["params"] == {"threadId": "thread-1", "includeTurns": True}
        server.reply(read, thread_result(turns=[]))

    thread = server.run(script)
    req = ProviderOperationRequest(
        OWNER, JOURNEY, "op_" + "3" * 32, "provider.session.reconcile",
        {
            "provider": "codex",
            "target_operation_ref": "op_" + "1" * 32,
            "workspace_ref": "workspace-a",
            "config_digest": "cfg-a",
            "capability_digest": "cap-a",
            "native_thread_id": "thread-1",
            "native_turn_id": "turn-1",
            "history_limit": 20,
            "stream": True,
            "reason": "test",
        },
        None,
    )
    outcome = adapter_for(server).reconcile(req, emit=Events())
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "missing"
    assert outcome.result["side_effect_status"] == "indeterminate"
