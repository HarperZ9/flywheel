"""Claude reconcile mapping from owned history observations."""
from __future__ import annotations

from pathlib import Path

from .claude_session_history import (
    load_owned_history, load_owned_terminal_observation,
    observe_source_history,
)
from .provider_session_contract import (
    ProviderOperationOutcome,
    ProviderOperationRequest,
    ProviderRuntimeBinding,
    ProviderSessionError,
)

_BINDING_DRIFT_DETAILS = {
    "native_session_mismatch",
    "source_operation_mismatch",
    "input_mismatch",
    "provider_mismatch",
}
_SESSION_KEYS = (
    "provider", "native_session_id", "native_thread_id", "native_turn_id",
    "last_provider_event_id", "config_digest", "capability_digest",
)


def reconcile_outcome(request: ProviderOperationRequest,
                      binding: ProviderRuntimeBinding) -> ProviderOperationOutcome:
    source = request.source_provider_session or {}
    session = _source_session(source, binding)
    target_ref = request.operation.get("target_operation_ref")
    if not isinstance(target_ref, str) or not target_ref:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    records, terminal = _runtime_evidence(request)
    source_context = dict(request.source_context or {})
    observed = observe_source_history(
        records,
        {
            "operation_ref": target_ref,
            "input_sha256": source_context.get("input_sha256", ""),
            "input_receipt_sha256": source_context.get("input_receipt_sha256", ""),
            "result_sha256": source_context.get("result_sha256", ""),
            "terminal_event_sha256": source_context.get("terminal_event_sha256", ""),
            "trace_head_sha256": source_context.get("trace_head_sha256", ""),
            "side_effect_status": source_context.get("side_effect_status", ""),
            "provider_session": session,
        },
        terminal,
    )
    if observed.detail_code in _BINDING_DRIFT_DETAILS:
        return ProviderOperationOutcome.failed(
            "AGENT_BINDING_DRIFT", provider_session=session,
            history_status="indeterminate", side_effect_status="indeterminate",
            detail_code=observed.detail_code)
    if observed.status != "native_terminal_observed":
        history_status = "missing" if observed.status == "missing" else "indeterminate"
        return ProviderOperationOutcome.failed(
            "AGENT_NATIVE_INCOMPLETE", provider_session=session,
            history_status=history_status, side_effect_status="indeterminate",
            detail_code=observed.detail_code)
    return ProviderOperationOutcome.completed({
        "provider_session": observed.provider_session,
        "history_status": "complete",
        "side_effect_status": "native_terminal_observed",
        "native_history_available": True,
        "target_operation_ref": target_ref,
        "provider_observation": _provider_observation(
            observed.provider_session, target_ref),
        "positive_observation_ref": {
            "kind": "claude_owned_terminal_observation",
            "last_provider_event_id": observed.last_provider_event_id,
            "terminal_result_sha256": observed.terminal_result_sha256,
            "history_store_head_sha256": observed.history_store_head_sha256,
        },
    })


def _source_session(source: dict, binding: ProviderRuntimeBinding) -> dict:
    if source.get("provider") != "claude":
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    if not isinstance(source.get("native_session_id"), str) or not source["native_session_id"]:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    session = {key: source.get(key, "") for key in _SESSION_KEYS}
    for key, actual in (("config_digest", binding.config_digest),
                        ("capability_digest", binding.capability_digest)):
        if session.get(key) and session[key] != actual:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        session[key] = actual
    return session


def _runtime_evidence(request: ProviderOperationRequest) -> tuple[list[dict], dict | None]:
    evidence = request.runtime_evidence or {}
    state_root = Path(request.state_root) if request.state_root is not None else None
    if type(evidence) is not dict or state_root is None:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", provider_session=dict(
                request.source_provider_session or {}),
            history_status="indeterminate", side_effect_status="indeterminate",
            detail_code="missing_runtime_evidence")
    history_pointer = evidence.get("owned_history")
    terminal_pointer = evidence.get("terminal_observation")
    if history_pointer is None:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", provider_session=dict(
                request.source_provider_session or {}),
            history_status="indeterminate", side_effect_status="indeterminate",
            detail_code="missing_runtime_evidence")
    records = load_owned_history(history_pointer, state_root=state_root)
    if terminal_pointer is None:
        return records, None
    return (
        records,
        load_owned_terminal_observation(terminal_pointer, state_root=state_root),
    )


def _provider_observation(session: dict, target_ref: str) -> dict:
    return {
        **{key: session.get(key, "") for key in _SESSION_KEYS},
        "target_operation_ref": target_ref,
        "observed_status": "native_terminal_observed",
    }
