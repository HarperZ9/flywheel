"""Shape helpers for provider-native gateway operations."""
from __future__ import annotations

from .gateway_operation import OPERATION_REF_PATTERN, _text
from .journey_types import SHA256_PATTERN
from .provider_session_runtime_binding import PROVIDER_BINDING_REF_PATTERN


def validate_provider_operation_shape(action: str, value: dict) -> None:
    if action == "provider.session.approval.respond":
        return _validate_approval_response(value)
    if value["provider"] not in {"codex", "claude"}:
        raise ValueError
    for key in ("workspace_ref", "config_digest", "provider_binding_ref"):
        if not _text(value[key]):
            raise ValueError
    if PROVIDER_BINDING_REF_PATTERN.fullmatch(value["provider_binding_ref"]) is None:
        raise ValueError
    if "capability_digest" in value and not _text(value["capability_digest"]):
        raise ValueError
    if "timeout_s" in value: _bounded_int(value["timeout_s"], 1, 1800)
    if "history_limit" in value: _bounded_int(value["history_limit"], 1, 200)
    for key in ("source_operation_ref", "target_operation_ref"):
        if key in value and OPERATION_REF_PATTERN.fullmatch(value[key]) is None:
            raise ValueError
    for key in ("native_session_id", "native_thread_id", "native_turn_id",
                "last_provider_event_id", "client_user_message_id",
                "tool_policy_ref"):
        if key in value and not _text(value[key]):
            raise ValueError
    if "attachment_refs" in value and (type(value["attachment_refs"]) is not list
            or any(not _text(item) for item in value["attachment_refs"])):
        raise ValueError
    if action == "provider.session.turn":
        if value["resume_policy"] not in {
                "new_thread", "resume_after_reconcile",
                "reconcile_before_resend"}:
            raise ValueError
        if type(value["permission_scope"]) is not dict:
            raise ValueError
        if type(value["input"]) not in (dict, list, str):
            raise ValueError


def provider_destination(value: dict) -> dict:
    if "operation_ref" in value:
        return {"kind": "provider-approval", "ref": value["operation_ref"]}
    return {"kind": "provider-session",
            "ref": f"{value['provider']}:{value.get('native_thread_id', '')}"}


def provider_session_scopes() -> tuple[str, ...]:
    return ("network",)


def _bounded_int(value: object, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError


def _validate_approval_response(value: dict) -> None:
    if OPERATION_REF_PATTERN.fullmatch(value["operation_ref"]) is None:
        raise ValueError
    for key in ("native_request_id", "client_response_id"):
        if not _text(value[key]):
            raise ValueError
    if SHA256_PATTERN.fullmatch(value["request_identity"]) is None:
        raise ValueError
    decision = value["decision"]
    if decision == "allow":
        if type(value.get("updated_input")) is not dict:
            raise ValueError
    elif decision == "deny":
        if "updated_input" in value:
            raise ValueError
    else:
        raise ValueError
