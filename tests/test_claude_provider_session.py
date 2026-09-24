from harness.claude_session_transport import ClaudeSessionTransportError
from harness.provider_session_contract import ProviderApprovalDecision

from test_claude_provider_session_support import (
    Events,
    FakeClient,
    OPREF,
    ControlBeforeResult,
    adapter_for,
    operation,
    request,
    result_event,
)


def test_claude_adapter_observes_terminal_result_without_claiming_history_complete():
    client = FakeClient(events=[result_event()])
    events = Events()
    adapter = adapter_for(client)

    outcome = adapter.start_turn(
        request(operation()), emit=events, request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert client.sent == [("text", "hello")]
    result = outcome.result
    assert result["provider_session"]["native_session_id"] == "claude-session-1"
    assert result["provider_session"].get("native_turn_id", "") == ""
    assert result["native_request_id"] == "msg-1"
    assert result["history_status"] == "missing_native_history"
    assert result["side_effect_status"] == "input_sent"
    assert result["native_turn_status"] == "success"
    assert adapter.launcher_calls["launcher"] == 0
    assert any(event["phase"] == "input_sent" for event in events.events)


def test_claude_adapter_treats_input_write_uncertainty_as_incomplete():
    error = ClaudeSessionTransportError("write_uncertain", "frame may have reached provider")
    client = FakeClient(write_error=error)

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert outcome.result["history_status"] == "indeterminate"
    assert outcome.result["side_effect_status"] == "write_uncertain"
    assert outcome.result["transport_uncertainty"] == "write_uncertain"


def test_claude_adapter_denies_stale_permission_decision_by_identity():
    observed = []
    client = ControlBeforeResult()

    def stale_approval(provider_request):
        observed.append(provider_request)
        return ProviderApprovalDecision(
            "allow", "wrong-identity", "", {"command": "pwd"})

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=stale_approval,
        cancelled=lambda: False)

    assert outcome.state == "completed"
    assert observed[0].provider == "claude"
    assert observed[0].native_request_id == "req-1"
    assert observed[0].native_item_id == "tool-1"
    assert client.decisions[0][1].behavior == "deny"
    assert client.decisions[0][1].message == "approval unavailable"


def test_claude_adapter_interrupt_ack_does_not_claim_actual_cancel_outcome():
    client = FakeClient()
    checks = iter([False, True, True])

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: next(checks))

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_CANCELLED"
    assert outcome.result["cancellation_status"] == "acknowledged"
    assert outcome.result["cancellation_outcome"] == "indeterminate"
    assert outcome.result["side_effect_status"] == "input_sent"
    assert client.interrupt_calls == 1


def test_claude_adapter_rejects_observed_session_mismatch_after_input():
    client = FakeClient(events=[result_event("actual-session")])

    outcome = adapter_for(client).start_turn(
        request(operation(native_session_id="expected-session")),
        emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert outcome.result["side_effect_status"] == "input_sent"
    assert outcome.result["observed_native_session_id"] == "actual-session"


def test_claude_resume_and_reconcile_are_explicitly_unsupported_without_history_proof():
    adapter = adapter_for(FakeClient())
    source = {"provider": "claude", "native_session_id": "s1"}

    resume = adapter.resume(
        request(operation(source_operation_ref=OPREF), source=source,
                action="provider.session.resume"), emit=Events())
    reconcile = adapter.reconcile(
        request(operation(target_operation_ref=OPREF), source=source,
                action="provider.session.reconcile"), emit=Events())

    assert resume.state == "failed"
    assert resume.result["reason"] == "AGENT_NATIVE_UNSUPPORTED"
    assert resume.result["history_status"] == "unsupported"
    assert resume.result["side_effect_status"] == "none"
    assert reconcile.state == "failed"
    assert reconcile.result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert reconcile.result["history_status"] == "indeterminate"
    assert reconcile.result["detail_code"] == "missing_runtime_evidence"
    assert reconcile.result["side_effect_status"] == "indeterminate"
    assert adapter.launcher_calls["launcher"] == 0
