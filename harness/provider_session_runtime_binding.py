"""Provider-session runtime binding snapshots and binding read validation."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .evidence_json import canonical_sha256
from .evidence_public import exact_request, parse_json
from .gateway_operation import GatewayOperationError
from .gateway_secret_boundary import validate_no_raw_secrets
from .journey_store import JourneyStore, JourneyStoreError
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN

BINDING_SCHEMA = "flywheel.provider-session-runtime-binding/v1"
BINDING_REQUEST_SCHEMA = "flywheel.provider-session-binding-request/v1"
PROVIDER_BINDING_REF_PATTERN = re.compile(r"psb_[0-9a-f]{32}\Z")
_REQUEST_REQUIRED = {
    "schema", "journey_ref", "expected_event_head", "provider",
    "workspace_ref", "permission_scope",
}
_REQUEST_OPTIONAL = {"model", "tool_policy_ref", "config_digest", "capability_digest"}
_RESPONSE_KEYS = {
    "schema", "provider", "owner_ref", "journey_ref", "workspace_ref",
    "model", "permission_scope_sha256", "config_digest", "capability_digest",
    "provider_binding_ref", "admitted", "reason", "limitations",
    "runtime_kind", "observed_at_event_head",
}


def binding_route_body(raw: bytes, *, owner_ref: str, state_root: Path, registry) -> dict:
    body = parse_json(raw)
    exact_request(body, _REQUEST_REQUIRED, optional=_REQUEST_OPTIONAL)
    validate_no_raw_secrets(body)
    if (body.get("schema") != BINDING_REQUEST_SCHEMA
            or JOURNEY_REF_PATTERN.fullmatch(body.get("journey_ref", "")) is None
            or SHA256_PATTERN.fullmatch(body.get("expected_event_head", "")) is None
            or body.get("provider") not in {"codex", "claude"}
            or not _text(body.get("workspace_ref"))
            or type(body.get("permission_scope")) is not dict
            or ("model" in body and not _text(body["model"]))
            or ("tool_policy_ref" in body and not _text(body["tool_policy_ref"]))):
        raise GatewayOperationError("INVALID_REQUEST")
    store = JourneyStore(state_root)
    try:
        store._validate_selector(owner_ref, body["journey_ref"])
        journey_dir = store._journey_dir(owner_ref, body["journey_ref"])
        if not journey_dir.exists():
            raise JourneyStoreError("JOURNEY_NOT_FOUND")
        current = store._read_head(journey_dir)
        if current is None:
            raise JourneyStoreError("JOURNEY_NOT_FOUND")
        store._events_at_head(journey_dir, current)
        head = current["event_head_sha256"]
    except JourneyStoreError as exc:
        raise GatewayOperationError(
            "PERMISSION_REQUIRED" if exc.code == "JOURNEY_NOT_FOUND" else exc.code) from None
    if head != body["expected_event_head"]:
        raise GatewayOperationError("HEAD_CONFLICT")
    operation = {k: body[k] for k in (
        "provider", "workspace_ref", "permission_scope", "model", "tool_policy_ref") if k in body}
    return binding_snapshot(registry, owner_ref=owner_ref,
        journey_ref=body["journey_ref"], expected_event_head=head,
        operation=operation, state_root=state_root)


def binding_snapshot(registry, **kwargs) -> dict:
    if registry is None:
        from .provider_session_registry import EmptyProviderSessionRuntimeRegistry
        registry = EmptyProviderSessionRuntimeRegistry()
    try:
        raw = registry.binding_snapshot(**kwargs)
    except GatewayOperationError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "AGENT_NATIVE_RUNTIME_DISABLED")
        raise GatewayOperationError(code) from None
    return normalize_binding_snapshot(raw, **kwargs)


def normalize_binding_snapshot(value: Any, *, owner_ref: str, journey_ref: str,
                               expected_event_head: str, operation: dict,
                               **_) -> dict:
    if type(value) is not dict:
        raise GatewayOperationError("AGENT_NATIVE_RUNTIME_DISABLED")
    result = {key: value.get(key) for key in _RESPONSE_KEYS}
    result["schema"] = BINDING_SCHEMA
    result["owner_ref"] = owner_ref
    result["journey_ref"] = journey_ref
    result["provider"] = operation["provider"]
    result["workspace_ref"] = operation["workspace_ref"]
    result["model"] = str(operation.get("model") or value.get("model") or "")
    result["permission_scope_sha256"] = canonical_sha256(
        operation.get("permission_scope", {}))
    result["observed_at_event_head"] = expected_event_head
    result["admitted"] = bool(value.get("admitted"))
    result["reason"] = str(value.get("reason") or (
        "admitted" if result["admitted"] else "AGENT_NATIVE_RUNTIME_DISABLED"))
    limitations = value.get("limitations", ())
    if type(limitations) is not list and type(limitations) is not tuple:
        raise GatewayOperationError("AGENT_NATIVE_RUNTIME_DISABLED")
    result["limitations"] = [str(item) for item in limitations if _text(str(item))]
    result["runtime_kind"] = str(value.get("runtime_kind") or "disabled")
    for key in ("config_digest", "capability_digest"):
        if not _text(value.get(key)):
            raise GatewayOperationError("AGENT_NATIVE_RUNTIME_DISABLED")
        result[key] = str(value[key])
    ref = value.get("provider_binding_ref")
    if not (type(ref) is str and PROVIDER_BINDING_REF_PATTERN.fullmatch(ref)):
        ref = "psb_" + canonical_sha256({
            key: result[key] for key in sorted(result)
            if key not in {"provider_binding_ref"}
        })[:32]
    result["provider_binding_ref"] = ref
    validate_no_raw_secrets(result)
    return result


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())
