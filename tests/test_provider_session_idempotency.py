from harness.provider_session_contract import (
    ProviderApprovalDecision,
    ProviderApprovalRequest,
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)

from provider_session_fixtures import (
    dispatch,
    operation_result,
    provider_factory,
    service_with_journey,
    turn_raw,
)


class TurnAdapter:
    provider = "codex"

    def __init__(self):
        self.turn_calls = 0
        self.approval_decisions = []

    def current_binding(self):
        return ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest="cfg-a", capability_digest="cap-a")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.turn_calls += 1
        decision = request_approval(ProviderApprovalRequest(
            provider="codex", native_request_id="approval-1",
            tool="write_file", payload_sha256="b" * 64,
            native_thread_id="thread-1", native_turn_id="turn-1",
            native_item_id="item-1"))
        self.approval_decisions.append(decision.behavior)
        emit.native("input_sent", native_thread_id="thread-1")
        return ProviderOperationOutcome.completed({
            "provider_session": {
                "provider": "codex",
                "native_session_id": "session-1",
                "native_thread_id": "thread-1",
                "native_turn_id": "turn-1",
                "last_provider_event_id": "event-1",
                "config_digest": "cfg-a",
                "capability_digest": "cap-a",
            },
            "history_status": "complete",
            "side_effect_status": "input_sent",
            "approval_behavior": decision.behavior,
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume should not be called")

    def reconcile(self, request, *, emit):
        raise AssertionError("reconcile should not be called")


def test_exact_replay_does_not_send_duplicate_provider_input(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = TurnAdapter()
    factory = provider_factory(adapters={"codex": adapter})
    raw = turn_raw(head)

    dispatch(service, raw, factory)
    replay = dispatch(service, raw, factory)

    assert replay.status == 200
    assert adapter.turn_calls == 1
    assert operation_result(service)["provider_session"]["native_thread_id"] == "thread-1"


def test_changed_replay_fails_before_second_provider_input(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = TurnAdapter()
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    changed = dispatch(
        service,
        turn_raw(head, input=[{"type": "input_text", "text": "changed"}]),
        factory,
    )

    assert changed.status == 409
    assert changed.body["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    assert adapter.turn_calls == 1


def test_permission_scope_never_auto_allows_provider_approval(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = TurnAdapter()

    dispatch(
        service,
        turn_raw(head, permission_scope={"mode": "auto"}),
        provider_factory(adapters={"codex": adapter}),
    )

    assert adapter.approval_decisions == ["deny"]
    assert operation_result(service)["approval_behavior"] == "deny"


def test_malformed_allow_approval_decision_is_denied(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = TurnAdapter()

    def malformed_allow(request, **_):
        return ProviderApprovalDecision("allow", request.identity(), "", None)

    dispatch(
        service, turn_raw(head),
        provider_factory(
            adapters={"codex": adapter}, approval_resolver=malformed_allow),
    )

    assert adapter.approval_decisions == ["deny"]
    assert operation_result(service)["approval_behavior"] == "deny"
