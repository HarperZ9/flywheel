import pytest

from harness.gateway_operation_route import operation_ref_for
from harness.provider_session_contract import (
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)

from provider_session_fixtures import (
    JOURNEY,
    OWNER,
    create_journey,
    dispatch,
    operation_result,
    provider_factory,
    reconcile_raw,
    service_with_journey,
    turn_raw,
)

OTHER_JOURNEY = "jrn_" + "b" * 32


class ProofAdapter:
    provider = "codex"

    def __init__(self, *, proof_mode="valid"):
        self.proof_mode = proof_mode
        self.turn_calls = 0
        self.reconcile_calls = 0

    def current_binding(self):
        return ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest="cfg-a", capability_digest="cap-a")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.turn_calls += 1
        turn_id = f"turn-{self.turn_calls}"
        emit.native(
            "input_sent", native_session_id="session-1",
            native_thread_id="thread-1", native_turn_id=turn_id,
            last_provider_event_id=f"event-{self.turn_calls}")
        return ProviderOperationOutcome.failed(
            "AGENT_NATIVE_INCOMPLETE",
            provider_session=_session(turn_id, f"event-{self.turn_calls}"),
            history_status="indeterminate",
            side_effect_status="unknown_after_send",
        ) if self.turn_calls == 1 else ProviderOperationOutcome.completed({
            "provider_session": _session(turn_id, f"event-{self.turn_calls}"),
            "history_status": "complete",
            "side_effect_status": "input_sent",
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume should not be called")

    def reconcile(self, request, *, emit):
        self.reconcile_calls += 1
        result = {
            "history_status": "confirmed_not_applied",
            "side_effect_status": "confirmed_not_applied",
            "provider_observation": _observation(
                request.operation["target_operation_ref"],
                "confirmed_not_applied"),
        }
        if self.proof_mode == "complete_none_no_observation":
            result = {
                "history_status": "complete",
                "side_effect_status": "none",
            }
        if self.proof_mode == "terminal_observed":
            result = {
                "history_status": "complete",
                "side_effect_status": "native_terminal_observed",
                "provider_observation": _observation(
                    request.operation["target_operation_ref"],
                    "native_terminal_observed"),
            }
        if self.proof_mode == "complete_wrong_observation":
            result = {
                "history_status": "complete",
                "side_effect_status": "native_terminal_observed",
                "provider_observation": _observation(
                    request.operation["target_operation_ref"],
                    "native_terminal_observed",
                    session=_session("turn-1", "event-1")
                    | {"native_thread_id": "wrong-thread"}),
            }
        if self.proof_mode == "complete_in_progress_observation":
            result = {
                "history_status": "complete",
                "side_effect_status": "in_progress",
                "provider_observation": _observation(
                    request.operation["target_operation_ref"],
                    "native_terminal_observed"),
            }
        if self.proof_mode == "mismatched_identity":
            result["target_operation_ref"] = request.operation["target_operation_ref"]
            result["provider_session"] = {
                "provider": "codex",
                "native_session_id": "other-session",
                "native_thread_id": "other-thread",
                "native_turn_id": "other-turn",
                "last_provider_event_id": "other-event",
                "config_digest": "cfg-other",
                "capability_digest": "cap-other",
            }
        return ProviderOperationOutcome.completed(result)


def test_stale_reconcile_proof_before_source_exists_does_not_unlock_turn(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ProofAdapter()
    factory = provider_factory(adapters={"codex": adapter})
    future_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")

    dispatch(
        service,
        reconcile_raw(head, request_id="reconcile-stale",
                      target_operation_ref=future_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )
    stale_ref = operation_ref_for(OWNER, JOURNEY, "reconcile-stale")
    assert operation_result(service, stale_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.reconcile_calls == 0

    head = service.snapshot(OWNER, stale_ref).event_head_sha256
    dispatch(service, turn_raw(head), factory)
    head = service.snapshot(OWNER, future_ref).event_head_sha256
    before = set(service.operation_refs(OWNER))
    dispatch(service, _resume_after_reconcile(head, future_ref), factory)

    new_ref = next(iter(service.operation_refs(OWNER) - before))
    assert operation_result(service, new_ref)["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert adapter.turn_calls == 1


def test_cross_journey_reconcile_proof_does_not_unlock_source_journey(tmp_path):
    service, head = service_with_journey(tmp_path)
    other_head = create_journey(
        tmp_path, journey_ref=OTHER_JOURNEY, request_id="other-genesis")
    adapter = ProofAdapter()
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    dispatch(
        service,
        reconcile_raw(
            other_head, request_id="other-reconcile",
            journey_ref=OTHER_JOURNEY, target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )

    proof_ref = operation_ref_for(OWNER, OTHER_JOURNEY, "other-reconcile")
    assert operation_result(service, proof_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.reconcile_calls == 0
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    before = set(service.operation_refs(OWNER))
    dispatch(service, _resume_after_reconcile(head, source_ref), factory)
    new_ref = next(iter(service.operation_refs(OWNER) - before))
    assert operation_result(service, new_ref)["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert adapter.turn_calls == 1


def test_mismatched_reconcile_native_identity_does_not_unlock_turn(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ProofAdapter(proof_mode="mismatched_identity")
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        reconcile_raw(head, target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )
    proof_ref = operation_ref_for(OWNER, JOURNEY, "reconcile-1")
    assert operation_result(service, proof_ref)["reason"] == "AGENT_BINDING_DRIFT"

    head = service.snapshot(OWNER, proof_ref).event_head_sha256
    before = set(service.operation_refs(OWNER))
    dispatch(service, _resume_after_reconcile(head, source_ref), factory)
    new_ref = next(iter(service.operation_refs(OWNER) - before))
    assert operation_result(service, new_ref)["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert adapter.turn_calls == 1


@pytest.mark.parametrize(
    ("proof_mode", "proof_reason"),
    [
        ("complete_none_no_observation", "AGENT_NATIVE_INCOMPLETE"),
        ("complete_in_progress_observation", "AGENT_NATIVE_INCOMPLETE"),
    ],
)
def test_complete_reconcile_without_terminal_observation_does_not_unlock_turn(
        tmp_path, proof_mode, proof_reason):
    _assert_reconcile_does_not_unlock(tmp_path, proof_mode, proof_reason)


def test_complete_reconcile_wrong_observation_does_not_unlock_turn(tmp_path):
    _assert_reconcile_does_not_unlock(
        tmp_path, "complete_wrong_observation", "AGENT_BINDING_DRIFT")


def _assert_reconcile_does_not_unlock(tmp_path, proof_mode, proof_reason):
    service, head = service_with_journey(tmp_path)
    adapter = ProofAdapter(proof_mode=proof_mode)
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        reconcile_raw(head, target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )

    proof_ref = operation_ref_for(OWNER, JOURNEY, "reconcile-1")
    assert operation_result(service, proof_ref)["reason"] == proof_reason
    head = service.snapshot(OWNER, proof_ref).event_head_sha256
    before = set(service.operation_refs(OWNER))
    dispatch(service, _resume_after_reconcile(head, source_ref), factory)
    new_ref = next(iter(service.operation_refs(OWNER) - before))
    assert operation_result(service, new_ref)["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert adapter.turn_calls == 1


@pytest.mark.parametrize("proof_mode", ["valid", "terminal_observed"])
def test_exact_reconcile_source_snapshot_unlocks_non_new_turn(tmp_path, proof_mode):
    service, head = service_with_journey(tmp_path)
    adapter = ProofAdapter(proof_mode=proof_mode)
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        reconcile_raw(head, target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )
    proof = operation_result(service, operation_ref_for(OWNER, JOURNEY, "reconcile-1"))
    assert proof["reconciliation_source"]["operation_ref"] == source_ref
    assert proof["source_provider_session"] == _session("turn-1", "event-1")

    head = service.snapshot(
        OWNER, operation_ref_for(OWNER, JOURNEY, "reconcile-1")).event_head_sha256
    dispatch(service, _resume_after_reconcile(head, source_ref), factory)

    assert adapter.turn_calls == 2


def _resume_after_reconcile(head, source_ref):
    return turn_raw(
        head, request_id="turn-2", resume_policy="resume_after_reconcile",
        source_operation_ref=source_ref, native_session_id="session-1",
        native_thread_id="thread-1", native_turn_id="turn-1")


def _session(turn_id, event_id):
    return {
        "provider": "codex",
        "native_session_id": "session-1",
        "native_thread_id": "thread-1",
        "native_turn_id": turn_id,
        "last_provider_event_id": event_id,
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
    }


def _observation(target_ref, observed_status, *, session=None):
    return {
        **(session or _session("turn-1", "event-1")),
        "target_operation_ref": target_ref,
        "observed_status": observed_status,
    }
