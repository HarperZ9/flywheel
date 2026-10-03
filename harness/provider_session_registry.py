"""Provider-session runtime registry interfaces and default disabled registry."""
from __future__ import annotations

from .evidence_json import canonical_sha256


class EmptyProviderSessionRuntimeRegistry:
    def binding_snapshot(self, *, owner_ref: str, journey_ref: str,
                         expected_event_head: str, operation: dict, **_) -> dict:
        material = {
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "event_head": expected_event_head,
            "provider": operation.get("provider", ""),
            "workspace_ref": operation.get("workspace_ref", ""),
            "permission_scope_sha256": canonical_sha256(
                operation.get("permission_scope", {})),
        }
        return {
            "schema": "flywheel.provider-session-runtime-binding/v1",
            "provider": operation.get("provider", ""),
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "workspace_ref": operation.get("workspace_ref", ""),
            "model": operation.get("model", ""),
            "permission_scope_sha256": material["permission_scope_sha256"],
            "config_digest": "disabled:" + canonical_sha256(material),
            "capability_digest": "disabled:" + canonical_sha256({
                **material, "capabilities": []}),
            "provider_binding_ref": "psb_" + canonical_sha256(material)[:32],
            "admitted": False,
            "reason": "AGENT_NATIVE_RUNTIME_DISABLED",
            "limitations": ["provider runtime registry is empty"],
            "runtime_kind": "disabled",
            "observed_at_event_head": expected_event_head,
        }

    def adapter_for(self, **_):
        return None


def runtime_registry(value):
    return value if value is not None else EmptyProviderSessionRuntimeRegistry()
