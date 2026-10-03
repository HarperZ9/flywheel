from harness.provider_session_contract import (
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)
from harness.provider_session_runner import ProviderSessionProcessFactory
from harness.provider_session_recovery import read_provider_trace
from harness.gateway_envelope import parse_gateway_envelope

from provider_session_fixtures import (
    dispatch,
    only_operation_ref,
    operation_result,
    provider_factory,
    reconcile_raw,
    service_with_journey,
    turn_raw,
)


class RecoveryAdapter:
    provider = "codex"

    def __init__(self, *, mode):
        self.mode = mode
        self.turn_calls = 0
        self.reconcile_calls = 0

    def current_binding(self):
        return ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest="cfg-a", capability_digest="cap-a")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.turn_calls += 1
        emit.native(
            "input_sent", native_session_id="session-1",
            native_thread_id="thread-1", native_turn_id="turn-1",
            last_provider_event_id="event-1")
        if self.mode == "disconnect_after_effect":
            return ProviderOperationOutcome.failed(
                "AGENT_NATIVE_INCOMPLETE",
                provider_session={
                    "provider": "codex",
                    "native_session_id": "session-1",
                    "native_thread_id": "thread-1",
                    "native_turn_id": "turn-1",
                    "last_provider_event_id": "event-1",
                    "config_digest": "cfg-a",
                    "capability_digest": "cap-a",
                },
                history_status="indeterminate",
                side_effect_status="unknown_after_send",
            )
        if self.mode == "response_write_uncertain":
            return ProviderOperationOutcome.completed({
                "history_status": "complete",
                "side_effect_status": "response_write_uncertain",
            })
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
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume should not be called")

    def reconcile(self, request, *, emit):
        self.reconcile_calls += 1
        return ProviderOperationOutcome.completed({
            "history_status": "confirmed_not_applied",
            "side_effect_status": "confirmed_not_applied",
        })


def test_disconnect_after_effect_records_write_ahead_intent_and_indeterminate(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = RecoveryAdapter(mode="disconnect_after_effect")

    dispatch(
        service, turn_raw(head),
        provider_factory(adapters={"codex": adapter}))

    ref = next(iter(service.operation_refs("owner_" + "a" * 32)))
    result = operation_result(service, ref)
    trace = read_provider_trace(tmp_path, "owner_" + "a" * 32, "jrn_" + "a" * 32, ref)
    assert result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert result["history_status"] == "indeterminate"
    assert result["side_effect_status"] == "unknown_after_send"
    assert [record["payload"]["phase"] for record in trace["records"][:2]] == [
        "dispatch_intent", "input_sent"]
    assert adapter.turn_calls == 1


def test_transport_write_uncertainty_is_not_clean_completion(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = RecoveryAdapter(mode="response_write_uncertain")

    dispatch(
        service, turn_raw(head),
        provider_factory(adapters={"codex": adapter}))

    ref = only_operation_ref(service)
    result = operation_result(service, ref)
    assert service.snapshot("owner_" + "a" * 32, ref).state == "failed"
    assert result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert result["history_status"] == "indeterminate"
    assert result["side_effect_status"] == "indeterminate"
    assert result["transport_uncertainty"] == "response_write_uncertain"


def test_non_new_turn_refuses_indeterminate_source_without_reconcile_proof(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = RecoveryAdapter(mode="disconnect_after_effect")
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = only_operation_ref(service)
    current_head = service.snapshot(
        "owner_" + "a" * 32, source_ref).event_head_sha256
    before = set(service.operation_refs("owner_" + "a" * 32))
    dispatch(
        service,
        turn_raw(
            current_head, request_id="turn-2",
            resume_policy="resume_after_reconcile",
            source_operation_ref=source_ref, native_session_id="session-1",
            native_thread_id="thread-1"),
        factory,
    )

    new_ref = next(iter(service.operation_refs("owner_" + "a" * 32) - before))
    result = operation_result(service, new_ref)
    assert result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert result["history_status"] == "indeterminate"
    assert result["side_effect_status"] == "indeterminate"
    assert adapter.turn_calls == 1


def test_provider_worker_close_records_indeterminate_frame(tmp_path):
    raw = turn_raw("0" * 64)
    envelope = parse_gateway_envelope("provider.session.turn", raw)
    authorized = type("Authorized", (), {
        "action": "provider.session.turn",
        "operation": envelope.operation.operation,
        "owner_ref": "owner_" + "a" * 32,
        "journey_ref": "jrn_" + "a" * 32,
        "client_request_id": "close-test",
    })()
    progress = []
    worker = ProviderSessionProcessFactory(
        state_root=tmp_path).create(authorized, progress.append)

    worker.close()

    trace = read_provider_trace(
        tmp_path, authorized.owner_ref, authorized.journey_ref,
        worker.operation_ref)
    assert trace["records"][0]["payload"]["phase"] == "close_indeterminate"
    assert progress[0]["provider_session"]["side_effect_status"] == "indeterminate"


def test_non_new_turn_rejects_caller_chosen_unknown_native_ids(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = RecoveryAdapter(mode="complete")
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = next(iter(service.operation_refs("owner_" + "a" * 32)))
    current_head = service.snapshot(
        "owner_" + "a" * 32, source_ref).event_head_sha256
    second = dispatch(
        service,
        turn_raw(
            current_head, request_id="turn-2", resume_policy="resume_after_reconcile",
            source_operation_ref=source_ref, native_thread_id="thread-evil"),
        factory,
    )

    assert second.status == 200
    result = operation_result(service, sorted(service.operation_refs("owner_" + "a" * 32))[-1])
    assert result["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.turn_calls == 1


def test_missing_history_does_not_become_confirmed_not_applied_without_proof(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = RecoveryAdapter(mode="complete")
    target_ref = "op_" + "c" * 32

    dispatch(
        service,
        reconcile_raw(head, target_operation_ref=target_ref),
        provider_factory(adapters={"codex": adapter}),
        path="/api/provider-sessions/reconcile",
    )

    result = operation_result(service)
    assert result["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.reconcile_calls == 0
