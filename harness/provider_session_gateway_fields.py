"""Gateway action and path declarations for native provider sessions."""
from __future__ import annotations

PROVIDER_SESSION_ACTIONS = frozenset((
    "provider.session.turn",
    "provider.session.resume",
    "provider.session.reconcile",
    "provider.session.approval.respond",
))

PROVIDER_SESSION_PATHS = {
    "/api/provider-sessions/turn": "provider.session.turn",
    "/api/provider-sessions/resume": "provider.session.resume",
    "/api/provider-sessions/reconcile": "provider.session.reconcile",
}


def provider_session_fields(ref_fields: set[str]) -> dict[str, tuple[set[str], set[str]]]:
    common = {
        "provider", "workspace_ref", "config_digest", "provider_binding_ref",
        "stream"} | ref_fields
    return {
        "provider.session.turn": (
            common | {"permission_scope", "input", "resume_policy"},
            {"model", "native_session_id", "native_thread_id", "native_turn_id",
             "client_user_message_id", "source_operation_ref", "timeout_s",
             "attachment_refs", "tool_policy_ref", "capability_digest"}),
        "provider.session.resume": (
            common | {"source_operation_ref"},
            {"native_session_id", "native_thread_id", "last_provider_event_id",
             "history_limit", "capability_digest", "timeout_s"}),
        "provider.session.reconcile": (
            common | {"target_operation_ref", "reason"},
            {"native_session_id", "native_thread_id", "last_provider_event_id",
             "history_limit", "capability_digest", "timeout_s"}),
        "provider.session.approval.respond": (
            {"operation_ref", "native_request_id", "request_identity",
             "decision", "client_response_id"} | ref_fields,
            {"updated_input"}),
    }
