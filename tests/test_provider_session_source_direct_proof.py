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
    service_with_journey,
    turn_raw,
)


OTHER_JOURNEY = "jrn_" + "b" * 32


class DirectProofAdapter:
    provider = "codex"

    def __init__(self, *, first_status="clean", session_changes=None,
                 session_omissions=()):
        self.first_status = first_status
        self.session_changes = dict(session_changes or {})
        self.session_omissions = tuple(session_omissions)
        self.turn_calls = 0
        self.sources = []

    def current_binding(self):
        return ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest="cfg-a", capability_digest="cap-a")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.turn_calls += 1
        self.sources.append(request.source_context)
        turn_id = f"turn-{self.turn_calls}"
        emit.native(
            "input_sent", native_session_id="session-1",
            native_thread_id="thread-1", native_turn_id=turn_id,
            last_provider_event_id=f"event-{self.turn_calls}")
        if self.turn_calls == 1:
            return self._first_turn(request)
        return ProviderOperationOutcome.completed({
            "provider_session": _session(turn_id, f"event-{self.turn_calls}"),
            "history_status": "complete",
            "side_effect_status": "input_sent",
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume should not be called")

    def reconcile(self, request, *, emit):
        raise AssertionError("reconcile should not be called")

    def _first_turn(self, request):
        if self.first_status == "incomplete":
            return ProviderOperationOutcome.failed(
                "AGENT_NATIVE_INCOMPLETE",
                provider_session=_session("turn-1", "event-1"),
                history_status="indeterminate",
                side_effect_status="unknown_after_send",
            )
        session = _session("turn-1", "event-1") | self.session_changes
        for key in self.session_omissions:
            session.pop(key, None)
        return ProviderOperationOutcome.completed({
            "provider_session": session,
            "history_status": "complete",
            "side_effect_status": "native_terminal_observed",
            "provider_observation": _observation(
                request.operation_ref, "native_terminal_observed",
                session=session),
        })


def test_clean_terminal_source_directly_unlocks_followup_turn(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = DirectProofAdapter()
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(service, _followup(head, source_ref), factory)

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["history_status"] == "complete"
    assert adapter.turn_calls == 2
    assert adapter.sources[1]["operation_ref"] == source_ref


def test_incomplete_source_still_requires_later_reconcile(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = DirectProofAdapter(first_status="incomplete")
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(service, _followup(head, source_ref), factory)

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert adapter.turn_calls == 1


def test_cross_journey_terminal_source_cannot_be_forged_by_ids(tmp_path):
    service, head = service_with_journey(tmp_path)
    other_head = create_journey(
        tmp_path, journey_ref=OTHER_JOURNEY, request_id="other-genesis")
    adapter = DirectProofAdapter()
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(
        service, turn_raw(other_head, journey_ref=OTHER_JOURNEY), factory)
    source_ref = operation_ref_for(OWNER, OTHER_JOURNEY, "turn-1")
    dispatch(service, _followup(head, source_ref), factory)

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.turn_calls == 1


def test_mismatched_native_ids_cannot_use_direct_terminal_source(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = DirectProofAdapter()
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        _followup(head, source_ref, native_thread_id="wrong-thread"),
        factory,
    )

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.turn_calls == 1


def test_source_capability_drift_cannot_use_direct_terminal_source(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = DirectProofAdapter(
        session_changes={"capability_digest": "cap-old"})
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(service, _followup(head, source_ref), factory)

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.turn_calls == 1


@pytest.mark.parametrize("missing_fields", [
    ("config_digest",),
    ("capability_digest",),
    ("config_digest", "capability_digest"),
])
def test_missing_source_binding_fields_cannot_use_direct_terminal_source(
        tmp_path, missing_fields):
    service, head = service_with_journey(tmp_path)
    adapter = DirectProofAdapter(session_omissions=missing_fields)
    factory = provider_factory(adapters={"codex": adapter})

    dispatch(service, turn_raw(head), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(service, _followup(head, source_ref), factory)

    followup_ref = operation_ref_for(OWNER, JOURNEY, "turn-2")
    assert operation_result(service, followup_ref)["reason"] == "AGENT_BINDING_DRIFT"
    assert adapter.turn_calls == 1


def _followup(head, source_ref, **changes):
    operation = {
        "request_id": "turn-2",
        "resume_policy": "resume_after_reconcile",
        "source_operation_ref": source_ref,
        "native_session_id": "session-1",
        "native_thread_id": "thread-1",
        "native_turn_id": "turn-1",
    }
    operation.update(changes)
    return turn_raw(head, **operation)


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


def _observation(target_ref, observed_status, *, session):
    return {
        **session,
        "target_operation_ref": target_ref,
        "observed_status": observed_status,
    }
