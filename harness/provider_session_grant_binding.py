"""Grant-time provider-session binding freeze and review helpers."""
from __future__ import annotations

from .gateway_operation import GatewayOperationError, thaw_operation
from .plan_run_snapshot import freeze_json, thaw_json
from .provider_session_runtime_binding import binding_snapshot

_BINDING_ACTIONS = {
    "provider.session.turn", "provider.session.resume",
    "provider.session.reconcile",
}
_REVIEW_KEYS = (
    "schema", "provider", "workspace_ref", "model", "config_digest",
    "capability_digest", "provider_binding_ref", "admitted", "reason",
    "limitations", "runtime_kind", "observed_at_event_head",
)


def freeze_provider_session_binding(operation, *, owner_ref=None, journey_ref=None,
                                    expected_event_head=None, state_root=None,
                                    workspace_root=None, registry=None):
    if operation.action not in _BINDING_ACTIONS:
        return None
    if not (owner_ref and journey_ref and expected_event_head and state_root is not None):
        return None
    op = thaw_operation(operation.operation)
    current = binding_snapshot(registry, owner_ref=owner_ref,
        journey_ref=journey_ref, expected_event_head=expected_event_head,
        operation=op, state_root=state_root, workspace_root=workspace_root)
    _compare_operation(op, current)
    return freeze_json(current)


def validate_provider_session_binding(value, operation) -> None:
    if operation.action not in _BINDING_ACTIONS:
        return
    if type(value) is not dict:
        raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    _compare_operation(thaw_operation(operation.operation), value)


def compare_provider_session_binding(record, plan) -> None:
    if record["action"] not in _BINDING_ACTIONS:
        return
    if "provider_session_binding" not in record:
        raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    if freeze_json(record["provider_session_binding"]) != plan.provider_session_binding:
        raise GatewayOperationError("AGENT_BINDING_DRIFT")


def review_provider_session_binding(record: dict) -> dict:
    binding = record.get("provider_session_binding")
    if binding is None:
        return {"status": "reprepare_required"}
    return {key: thaw_json(freeze_json(binding)).get(key) for key in _REVIEW_KEYS}


def _compare_operation(operation: dict, binding: dict) -> None:
    checks = (("provider", True), ("workspace_ref", True),
              ("config_digest", True), ("capability_digest",
              "capability_digest" in operation), ("provider_binding_ref", True),
              ("model", "model" in operation))
    for key, enabled in checks:
        if enabled:
            expected = operation.get(key)
            if (type(expected) is not str or not expected.strip()
                    or binding.get(key) != expected):
                raise GatewayOperationError("AGENT_BINDING_DRIFT")
