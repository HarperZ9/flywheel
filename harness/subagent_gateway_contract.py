"""Shared v2 subagent gateway route receipt contract."""
from __future__ import annotations

SPAWN_SCHEMA_V2 = "flywheel.subagent-spawn-request/v2"
SPEC_SCHEMA_V2 = "flywheel.subagent-spec/v2"
ROUTING_SCHEMA_V2 = "flywheel.subagent-routing/v2"
PARENT_AUTHORITY_SCHEMA = "flywheel.subagent-parent-authority/v1"
ROUTE_EVIDENCE_SCHEMA = "flywheel.subagent-route-evidence/v1"
RESERVATION_SCHEMA = "flywheel.subagent-budget-reservation/v1"
_ROUTE_FIELDS = {"endpoint", "model", "execution_mode", "tool_protocol",
                 "max_steps", "max_tokens", "timeout_s", "credential_refs"}


def route_summary(binding: dict, operation_sha256: str) -> dict:
    protocol = binding.get("tool_protocol") or {}
    return {"schema": ROUTING_SCHEMA_V2, "operation_sha256": operation_sha256,
        "endpoint": binding["endpoint"]["name"],
        "adapter": binding["endpoint"]["adapter"],
        "execution_mode": binding.get("execution_mode", "api"),
        "model_id": binding["model"]["model_id"],
        "model_selection": binding["model"]["selection"],
        "requested_model_reference": binding["model"].get("requested_model_reference"),
        "tool_protocol": protocol.get("protocol", "compatibility"),
        "native_api_route": protocol.get("native_api_route"),
        "budget": dict(binding["budget"]),
        "capabilities": dict(binding["capabilities"])}


def spec_live_fields(spec: dict) -> dict:
    if spec.get("schema") != SPEC_SCHEMA_V2:
        return {}
    return {"route": spec.get("route"), "operation_ref": spec.get("operation_ref"),
        "operation_sha256": spec.get("operation_sha256"),
        "agent_binding_sha256": spec.get("agent_binding_sha256")}


def spec_receipt_fields(spec: dict, result: dict | None) -> dict:
    if spec.get("schema") != SPEC_SCHEMA_V2:
        return {}
    result = result or {}
    return {"routing_schema": ROUTING_SCHEMA_V2, "route": spec.get("route"),
        "operation_ref": spec.get("operation_ref", ""),
        "operation_sha256": spec.get("operation_sha256", ""),
        "agent_binding_sha256": spec.get("agent_binding_sha256", ""),
        "gateway_projection": result.get("gateway_projection"),
        "gateway_operation": result.get("gateway_operation"),
        "route_evidence": result.get("route_evidence"),
        "usage": result.get("usage")}
