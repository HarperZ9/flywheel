"""Approval helpers for Codex provider sessions."""
from __future__ import annotations

from .codex_session_types import CodexServerRequest, CodexSessionTransportError
from .evidence_json import canonical_sha256
from .provider_session_contract import (
    ProviderApprovalDecision, ProviderApprovalRequest, ProviderSessionError,
)

_APPROVAL_DENIAL = {
    "item/commandExecution/requestApproval": {"decision": "decline"},
    "item/fileChange/requestApproval": {"decision": "decline"},
    "item/permissions/requestApproval": {"permissions": {}},
    "applyPatchApproval": {"decision": "denied"},
    "execCommandApproval": {"decision": "denied"},
}
_APPROVAL_ALLOW = {
    "item/commandExecution/requestApproval": {
        "accept", "acceptForSession", "decline", "cancel"},
    "item/fileChange/requestApproval": {
        "accept", "acceptForSession", "decline", "cancel"},
    "applyPatchApproval": {
        "approved", "approved_for_session", "denied", "timed_out", "abort"},
    "execCommandApproval": {
        "approved", "approved_for_session", "denied", "timed_out", "abort"},
}
def _provider_approval(server_request: CodexServerRequest, session: dict):
    params = server_request.params if isinstance(server_request.params, dict) else {}
    return ProviderApprovalRequest(
        provider="codex",
        native_request_id=str(server_request.id),
        tool=server_request.method,
        payload_sha256=canonical_sha256(params),
        native_session_id=session.get("native_session_id", ""),
        native_thread_id=str(params.get("threadId") or params.get("conversationId") or ""),
        native_turn_id=str(params.get("turnId") or ""),
        native_item_id=str(params.get("itemId") or params.get("callId") or ""),
    )


def _approval_matches_session(
        server_request: CodexServerRequest, session: dict) -> bool:
    params = server_request.params if isinstance(server_request.params, dict) else {}
    thread_id = params.get("threadId") or params.get("conversationId")
    turn_id = params.get("turnId")
    return (
        thread_id == session.get("native_thread_id")
        and turn_id == session.get("native_turn_id"))


def _approval_result(method: str, request: ProviderApprovalRequest, decision):
    if (not isinstance(decision, ProviderApprovalDecision)
            or decision.request_identity != request.identity()
            or decision.behavior != "allow"
            or not isinstance(decision.updated_input, dict)):
        return dict(_APPROVAL_DENIAL[method])
    if method == "item/permissions/requestApproval":
        permissions = decision.updated_input.get("permissions")
        if isinstance(permissions, dict):
            result = {"permissions": permissions}
            for key in ("scope", "strictAutoReview"):
                if key in decision.updated_input:
                    result[key] = decision.updated_input[key]
            return result
        return dict(_APPROVAL_DENIAL[method])
    native_decision = decision.updated_input.get("decision")
    if native_decision in _APPROVAL_ALLOW.get(method, set()):
        return {"decision": native_decision}
    return dict(_APPROVAL_DENIAL[method])


def _reply_or_fail(transport, server_request, session, **message) -> None:
    try:
        transport.reply(server_request, **message)
    except CodexSessionTransportError as exc:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", provider_session=dict(session),
            history_status="indeterminate",
            side_effect_status="unknown_after_send",
            transport_error=exc.code)
