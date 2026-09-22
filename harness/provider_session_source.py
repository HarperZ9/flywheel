"""Source-operation proof checks for provider-native session turns."""
from __future__ import annotations

from pathlib import Path

from .gateway_operation import OPERATION_REF_PATTERN
from .gateway_operation_validation import TERMINAL_EVENTS
from .provider_session_contract import (
    ProviderSessionError, validate_turn_policy,
)
from .provider_session_recovery import (
    latest_provider_session_from_trace, provider_session_from_result,
    read_provider_trace,
)

_RECONCILE_DISPOSITIONS = {
    ("complete", "native_terminal_observed"): "native_terminal_observed",
    ("confirmed_not_applied", "confirmed_not_applied"): "confirmed_not_applied",
}
_PROVIDER_OBSERVATION_KEYS = (
    "provider", "native_session_id", "native_thread_id", "native_turn_id",
    "last_provider_event_id", "config_digest", "capability_digest",
)


def source_context_for_operation(authorized, operation: dict, state_root: Path):
    if authorized.action == "provider.session.turn":
        source = _turn_source(authorized, operation, state_root)
        return source["provider_session"] if source else None, source
    if authorized.action == "provider.session.resume":
        session = _resume_source(authorized, operation, state_root)
        return session, None
    if authorized.action == "provider.session.reconcile":
        source = _source_snapshot(
            state_root, authorized.owner_ref, authorized.journey_ref,
            operation.get("target_operation_ref"))
        if source is None:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        return source["provider_session"], source
    return None, None


def bind_reconcile_result(operation: dict, result: dict,
                          source: dict | None) -> dict:
    if source is None:
        return result
    binding = _proof_binding(source)
    expected = {
        "target_operation_ref": source["operation_ref"],
        "source_operation_ref": source["operation_ref"],
        "source_journey_ref": source["journey_ref"],
        "source_terminal_event_sha256": source["terminal_event_sha256"],
        "source_result_sha256": source["result_sha256"],
        "source_input_sha256": source.get("input_sha256", ""),
        "source_input_receipt_sha256": source.get("input_receipt_sha256", ""),
        "source_provider_session": source["provider_session"],
        "reconciliation_source": binding,
    }
    if operation.get("target_operation_ref") != source["operation_ref"]:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    for key, value in expected.items():
        if key in result and result[key] != value:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
    if "provider_session" in result and result["provider_session"] != source["provider_session"]:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    _validate_reconcile_observation(result, source)
    return {**result, **expected, "provider_session": source["provider_session"]}


def _turn_source(authorized, operation: dict, state_root: Path):
    policy = validate_turn_policy(operation.get("resume_policy"))
    need_source = policy != "new_thread" or any(
        operation.get(key) for key in (
            "native_session_id", "native_thread_id", "native_turn_id"))
    if not need_source:
        return None
    source = _source_snapshot(
        state_root, authorized.owner_ref, authorized.journey_ref,
        operation.get("source_operation_ref"))
    if source is None:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    _check_native_ids(operation, source["provider_session"])
    _check_source_binding(operation, source["provider_session"])
    if _is_direct_terminal_source(source):
        return source
    if not _has_reconcile_proof(state_root, authorized.owner_ref,
                                authorized.journey_ref, source):
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", history_status="indeterminate",
            side_effect_status="indeterminate")
    return source


def _resume_source(authorized, operation: dict, state_root: Path):
    source_ref = operation.get("source_operation_ref")
    if type(source_ref) is not str or OPERATION_REF_PATTERN.fullmatch(source_ref) is None:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    source = _source_snapshot(
        state_root, authorized.owner_ref, authorized.journey_ref, source_ref)
    if source is not None:
        return source["provider_session"]
    return _trace_source(
        state_root, authorized.owner_ref, authorized.journey_ref, source_ref)


def _source_snapshot(state_root, owner_ref, journey_ref, operation_ref):
    if type(operation_ref) is not str or OPERATION_REF_PATTERN.fullmatch(operation_ref) is None:
        return None
    from .gateway_operations import GatewayOperations
    service = GatewayOperations(
        state_root, clock=lambda: "1970-01-01T00:00:00Z")
    try:
        journey = service._journey(owner_ref)
        history = service._history(journey, operation_ref, journey_ref)
        terminal = next(e for e in history if e["event_type"] in TERMINAL_EVENTS)
        value = service.result(owner_ref, operation_ref)
    except Exception:
        return None
    session = provider_session_from_result(value["result"])
    if not session:
        return None
    return {
        "journey_ref": journey_ref,
        "operation_ref": operation_ref,
        "action": value["action"],
        "state": value["state"],
        "terminal_event_sha256": terminal["event_sha256"],
        "terminal_sequence": terminal["sequence"],
        "result_sha256": terminal["payload"]["result_sha256"],
        "history_status": value["result"].get("history_status", ""),
        "side_effect_status": value["result"].get("side_effect_status", ""),
        **_input_receipt_from_trace(
            state_root, owner_ref, journey_ref, operation_ref),
        "trace_ref": value["result"].get("trace_ref", ""),
        "trace_head_sha256": value["result"].get("trace_head_sha256", ""),
        "record_count": value["result"].get("record_count", 0),
        "provider_session": session,
    }


def _trace_source(state_root, owner_ref, journey_ref, operation_ref):
    try:
        trace = read_provider_trace(state_root, owner_ref, journey_ref, operation_ref)
        return latest_provider_session_from_trace(trace["records"])
    except Exception:
        return None


def _check_native_ids(operation: dict, source: dict) -> None:
    for key in ("native_session_id", "native_thread_id", "native_turn_id"):
        if operation.get(key) and operation[key] != source.get(key):
            raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _check_source_binding(operation: dict, source: dict) -> None:
    for key in ("provider", "config_digest", "capability_digest"):
        if operation.get(key) and operation[key] != source.get(key):
            raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _is_direct_terminal_source(source: dict) -> bool:
    return (
        source["action"] == "provider.session.turn"
        and source["state"] == "completed"
        and source["history_status"] == "complete"
        and source["side_effect_status"] == "native_terminal_observed"
    )


def _has_reconcile_proof(state_root, owner_ref, journey_ref, source):
    from .gateway_operations import GatewayOperations
    service = GatewayOperations(
        state_root, clock=lambda: "1970-01-01T00:00:00Z")
    try:
        journey = service._journey(owner_ref)
        events = journey._events(journey_ref)
    except Exception:
        return False
    expected = _proof_binding(source)
    for event in events:
        if event["event_type"] != "operation_queued":
            continue
        ref = event["payload"].get("operation_ref")
        if ref == source["operation_ref"]:
            continue
        try:
            history = service._history(journey, ref, journey_ref)
            terminal = next(e for e in history if e["event_type"] in TERMINAL_EVENTS)
            value = service.result(owner_ref, ref)
        except Exception:
            continue
        if (value["action"] != "provider.session.reconcile"
                or value["state"] != "completed"
                or terminal["sequence"] <= source["terminal_sequence"]):
            continue
        result = value["result"]
        if result.get("reconciliation_source") != expected:
            continue
        if not _eligible_reconcile_result(result, source):
            continue
        return True
    return False


def _proof_binding(source):
    """Bind proof to immutable same-Journey events, not wallclock time.

    The source terminal event and sealed result digest prove the target existed
    before reconciliation was dispatched; later proof lookup also requires the
    reconcile terminal sequence to be after that source terminal in the same
    Journey event chain.
    """
    return {
        "journey_ref": source["journey_ref"],
        "operation_ref": source["operation_ref"],
        "terminal_event_sha256": source["terminal_event_sha256"],
        "terminal_sequence": source["terminal_sequence"],
        "result_sha256": source["result_sha256"],
        "state": source["state"],
        "history_status": source["history_status"],
        "side_effect_status": source["side_effect_status"],
        "input_sha256": source.get("input_sha256", ""),
        "input_receipt_sha256": source.get("input_receipt_sha256", ""),
        "trace_ref": source["trace_ref"],
        "trace_head_sha256": source["trace_head_sha256"],
        "record_count": source["record_count"],
        "provider_session": source["provider_session"],
    }


def _validate_reconcile_observation(result: dict, source: dict) -> None:
    observed_status = _reconcile_observed_status(result)
    if observed_status is None:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", history_status="indeterminate",
            side_effect_status="indeterminate")
    if "provider_observation" not in result:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", history_status="indeterminate",
            side_effect_status="indeterminate")
    if not _observation_matches(
            result["provider_observation"], source, observed_status):
        raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _eligible_reconcile_result(result: dict, source: dict) -> bool:
    observed_status = _reconcile_observed_status(result)
    return (observed_status is not None
            and _observation_matches(
                result.get("provider_observation"), source, observed_status))


def _reconcile_observed_status(result: dict) -> str | None:
    return _RECONCILE_DISPOSITIONS.get((
        result.get("history_status"), result.get("side_effect_status")))


def _observation_matches(observation, source: dict, observed_status: str) -> bool:
    return observation == _expected_observation(source, observed_status)


def _expected_observation(source: dict, observed_status: str) -> dict:
    session = source["provider_session"]
    return {
        **{key: session.get(key, "") for key in _PROVIDER_OBSERVATION_KEYS},
        "target_operation_ref": source["operation_ref"],
        "observed_status": observed_status,
    }


def _input_receipt_from_trace(state_root, owner_ref, journey_ref, operation_ref):
    try:
        trace = read_provider_trace(state_root, owner_ref, journey_ref, operation_ref)
    except Exception:
        return {}
    for record in trace["records"]:
        payload = record.get("payload") or {}
        if (record.get("kind") == "progress"
                and payload.get("phase") == "input_receipt"):
            value = payload.get("input_sha256")
            if type(value) is str and value:
                return {
                    "input_sha256": value,
                    "input_receipt_sha256": record["record_sha256"],
                }
    return {}
