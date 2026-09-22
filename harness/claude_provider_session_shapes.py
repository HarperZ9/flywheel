"""Small helpers for the Claude provider-session adapter."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .claude_session_contract import ClaudePermissionDecision
from .claude_session_contract import session_id_from_event
from .evidence_json import canonical_sha256
from .claude_session_wire import validate_result_frame
from .provider_session_contract import (
    ProviderApprovalDecision,
    ProviderApprovalRequest,
    ProviderOperationOutcome,
    ProviderOperationRequest,
    ProviderRuntimeBinding,
    ProviderSessionError,
)

UNCERTAIN_TRANSPORT = {"write_uncertain", "response_write_uncertain"}
FATAL_PROTOCOL = {
    "eof", "read_error", "malformed_json", "malformed_event",
    "line_overflow", "event_overflow", "session_id_mismatch",
    "cleanup_incomplete", "write_uncertain", "response_write_uncertain",
}


def require_surface(surface, client, operation: dict) -> None:
    if surface is None:
        raise _surface_error("missing_transport")
    required = {
        "event": ("next_event", "pop_event"),
        "protocol": ("next_protocol_event", "pop_protocol_event"),
        "control": ("next_control_request", "pop_control_request"),
    }
    for label, names in required.items():
        if not any(callable(getattr(surface, name, None)) for name in names):
            raise _surface_error(f"missing_{label}_surface")
    method = getattr(client, "send_permission_decision", None)
    if not callable(method):
        method = getattr(surface, "send_permission_decision", None)
    if not callable(method):
        raise _surface_error("missing_permission_response_surface")
    custody = (getattr(surface, "has_pending_control_requests", None),
               getattr(surface, "mark_recovery_needed", None))
    if not all(callable(method) for method in custody):
        raise _surface_error("missing_control_custody_surface")


def has_pending_controls(surface) -> bool:
    method = getattr(surface, "has_pending_control_requests", None)
    if not callable(method):
        raise _surface_error("missing_control_custody_surface")
    return bool(method())


def mark_recovery(surface) -> None:
    method = getattr(surface, "mark_recovery_needed", None)
    if not callable(method):
        raise _surface_error("missing_control_custody_surface")
    method()


def surface_session_id(surface) -> str:
    value = getattr(surface, "session_id", "")
    return value if isinstance(value, str) and value else ""


def _surface_error(kind: str) -> ProviderSessionError:
    return ProviderSessionError(
        "AGENT_NATIVE_PROTOCOL_ERROR", history_status="indeterminate",
        side_effect_status="none", surface_error=kind)


def send_input(client, value) -> None:
    if isinstance(value, str):
        client.send_text(value)
    elif isinstance(value, dict):
        client.send_blocks([value])
    elif isinstance(value, list):
        client.send_blocks(value)
    else:
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")


def pop_event(surface, *, timeout):
    method = getattr(surface, "next_event", None) or getattr(surface, "pop_event", None)
    return method(timeout=timeout) if callable(method) else None


def pop_control(surface):
    method = getattr(surface, "next_control_request", None) or getattr(surface, "pop_control_request", None)
    return method(timeout=0.0) if callable(method) else None


def pop_protocol(surface):
    method = getattr(surface, "next_protocol_event", None) or getattr(surface, "pop_protocol_event", None)
    return method(timeout=0.0) if callable(method) else None


def send_permission(client, surface, control, decision) -> None:
    method = getattr(client, "send_permission_decision", None) or getattr(surface, "send_permission_decision", None)
    if not callable(method):
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    method(control, decision)


def provider_approval(control, session: dict) -> ProviderApprovalRequest:
    request = plain_json(control.request)
    tool = str(request.get("tool_name") or request.get("subtype") or "unknown")
    return ProviderApprovalRequest(
        provider="claude", native_request_id=control.request_id, tool=tool,
        payload_sha256=canonical_sha256(request),
        native_session_id=session.get("native_session_id", ""),
        native_thread_id=session.get("native_thread_id", ""),
        native_turn_id=session.get("native_turn_id", ""),
        native_item_id=str(request.get("tool_use_id") or ""),
    )


def claude_decision(request: ProviderApprovalRequest, decision) -> ClaudePermissionDecision:
    if (isinstance(decision, ProviderApprovalDecision)
            and decision.request_identity == request.identity()):
        if decision.behavior == "allow" and isinstance(decision.updated_input, dict):
            return ClaudePermissionDecision.allow(decision.updated_input)
        if decision.behavior == "deny" and decision.message:
            return ClaudePermissionDecision.deny(decision.message)
    return ClaudePermissionDecision.deny("approval unavailable")


def result_outcome(request, session, event, native_request_id, cancel_ack):
    raw = event.raw if isinstance(event.raw, dict) else {}
    if not validate_result_frame(raw):
        return incomplete("malformed_result", session=session)
    session_id = event.session_id or raw.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return incomplete("missing_session_id", session=session)
    expected = request.operation.get("native_session_id")
    if expected and expected != session_id:
        return ProviderOperationOutcome.failed(
            "AGENT_BINDING_DRIFT", provider_session=dict(session),
            history_status="indeterminate", side_effect_status="input_sent",
            expected_native_session_id=expected,
            observed_native_session_id=session_id)
    observed = {**session, "native_session_id": session_id,
                "last_provider_event_id": f"event-{event.sequence}"}
    status = str(raw.get("subtype") or "")
    result = {
        "provider_session": observed,
        "native_request_id": native_request_id,
        "history_status": "missing_native_history",
        "side_effect_status": "input_sent",
        "native_history_available": False,
        "native_turn_status": status,
        "native_result_is_error": bool(raw.get("is_error")),
    }
    if cancel_ack:
        return ProviderOperationOutcome.failed(
            "AGENT_NATIVE_CANCELLED", **result,
            cancellation_status="acknowledged",
            cancellation_outcome=status or "indeterminate")
    if raw.get("is_error") or status not in {"success"}:
        return ProviderOperationOutcome.failed("AGENT_NATIVE_TURN_FAILED", **result)
    return ProviderOperationOutcome.completed(result)


def observe_event_session(session: dict, event) -> ProviderOperationOutcome | None:
    raw = event.raw if isinstance(event.raw, dict) else {}
    session_id = event.session_id or session_id_from_event(raw)
    if not session_id:
        return None
    current = session.get("native_session_id") or ""
    if current and current != session_id:
        return ProviderOperationOutcome.failed(
            "AGENT_BINDING_DRIFT", provider_session=dict(session),
            history_status="indeterminate", side_effect_status="input_sent",
            expected_native_session_id=current,
            observed_native_session_id=session_id)
    session["native_session_id"] = session_id
    return None


def base_session(binding: ProviderRuntimeBinding) -> dict:
    return {"provider": "claude", "native_session_id": "",
            "native_thread_id": "", "native_turn_id": "",
            "config_digest": binding.config_digest,
            "capability_digest": binding.capability_digest}


def session_event(request, session) -> dict:
    payload = dict(session)
    for key in ("source_operation_ref", "target_operation_ref"):
        if isinstance(request.operation.get(key), str):
            payload[key] = request.operation[key]
    return payload


def event_payload(request, session, event) -> dict:
    payload = session_event(request, session)
    payload.update({"raw_event_type": event.kind,
                    "last_provider_event_id": f"event-{event.sequence}"})
    if event.session_id:
        payload["native_session_id"] = event.session_id
    return payload


def native_request_id(request: ProviderOperationRequest) -> str:
    value = request.operation.get("client_user_message_id")
    return value if isinstance(value, str) and value else request.operation_ref


def input_receipt(request: ProviderOperationRequest) -> dict:
    value = request.operation.get("input")
    if isinstance(value, str):
        kind = "text"
    elif isinstance(value, (dict, list)):
        kind = "blocks"
    else:
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    request_id = native_request_id(request)
    receipt = {
        "native_request_id": request_id,
        "client_user_message_id": request_id,
        "input_sha256": canonical_sha256(plain_json(value)),
        "input_kind": kind,
    }
    source = request.operation.get("source_operation_ref")
    if isinstance(source, str) and source:
        receipt["source_operation_ref"] = source
    return receipt


def timeout(operation: dict, default: float) -> float:
    value = operation.get("timeout_s", default)
    return float(value) if isinstance(value, int) and value > 0 else default


def plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain_json(item) for item in value]
    if isinstance(value, list):
        return [plain_json(item) for item in value]
    return value


def unsupported() -> ProviderOperationOutcome:
    return ProviderOperationOutcome.failed(
        "AGENT_NATIVE_UNSUPPORTED", history_status="unsupported",
        side_effect_status="none",
        unsupported_reason="claude_native_history_reconcile_unavailable")


def incomplete(reason: str, *, session=None) -> ProviderOperationOutcome:
    result = {"history_status": "indeterminate",
              "side_effect_status": "unknown_after_send",
              "transport_error": reason}
    if session:
        result["provider_session"] = dict(session)
    return ProviderOperationOutcome.failed("AGENT_NATIVE_INCOMPLETE", **result)


def transport_failure(code: str, *, input_sent: bool, session=None) -> ProviderOperationOutcome:
    side = code if code in UNCERTAIN_TRANSPORT else ("unknown_after_send" if input_sent else "none")
    result = {"history_status": "indeterminate", "side_effect_status": side,
              "transport_error": code}
    if code in UNCERTAIN_TRANSPORT:
        result["transport_uncertainty"] = code
    if session:
        result["provider_session"] = dict(session)
    return ProviderOperationOutcome.failed("AGENT_NATIVE_INCOMPLETE", **result)


def cancelled(status: str, outcome: str, session: dict, *, side_effect="input_sent",
              transport_error: str = "") -> ProviderOperationOutcome:
    result = {"provider_session": dict(session), "history_status": "indeterminate",
              "side_effect_status": side_effect, "cancellation_status": status,
              "cancellation_outcome": outcome}
    if transport_error:
        result["transport_error"] = transport_error
    return ProviderOperationOutcome.failed("AGENT_NATIVE_CANCELLED", **result)
