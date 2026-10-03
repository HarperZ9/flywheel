"""In-memory live approval custody for provider-native sessions."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any

from .evidence_json import canonical_bytes
from .gateway_operation import GatewayOperationError, thaw_operation
from .gateway_secret_boundary import validate_no_raw_secrets
from .provider_session_contract import ProviderApprovalDecision


@dataclass
class _Pending:
    row: dict
    operation: dict
    decision: ProviderApprovalDecision | None = None


class ProviderApprovalBroker:
    def __init__(self, *, default_timeout_s: float = 120.0):
        self.default_timeout_s = max(0.01, float(default_timeout_s))
        self._condition = threading.Condition()
        self._pending: dict[tuple[str, str, str], _Pending] = {}

    def request(self, request, *, authorized, source_provider_session=None,
                timeout_s: float | None = None) -> ProviderApprovalDecision:
        identity = request.identity()
        operation = thaw_operation(authorized.operation)
        key = (authorized.owner_ref, _operation_ref(authorized), identity)
        row = {
            "operation_ref": key[1],
            "owner_ref": authorized.owner_ref,
            "journey_ref": authorized.journey_ref,
            "request_identity": identity,
            "provider": request.provider,
            "native_request_id": request.native_request_id,
            "native_session_id": request.native_session_id,
            "native_thread_id": request.native_thread_id,
            "native_turn_id": request.native_turn_id,
            "native_item_id": request.native_item_id,
            "tool": request.tool,
            "payload_sha256": request.payload_sha256,
            "config_digest": str(operation.get("config_digest", "")),
            "capability_digest": str(operation.get("capability_digest", "")),
            "state": "pending",
        }
        pending = _Pending(row=row, operation=operation)
        deadline = time.monotonic() + (timeout_s or self.default_timeout_s)
        with self._condition:
            if key in self._pending:
                return ProviderApprovalDecision.deny(request, "duplicate approval request")
            self._pending[key] = pending
            self._condition.notify_all()
            while pending.decision is None and pending.row["state"] == "pending":
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    pending.row["state"] = "expired"
                    self._pending.pop(key, None)
                    return ProviderApprovalDecision.deny(request, "approval timed out")
                self._condition.wait(remaining)
            self._pending.pop(key, None)
            if pending.decision is None:
                return ProviderApprovalDecision.deny(request, "approval unavailable")
            return pending.decision

    def pending(self, *, owner_ref: str, operation_ref: str) -> list[dict]:
        with self._condition:
            rows = [dict(item.row) for key, item in self._pending.items()
                    if key[0] == owner_ref and key[1] == operation_ref
                    and item.row["state"] == "pending"]
        return sorted(rows, key=lambda row: row["native_request_id"])

    def respond(self, authorized) -> dict:
        operation = thaw_operation(authorized.operation)
        key = (authorized.owner_ref, operation["operation_ref"],
               operation["request_identity"])
        with self._condition:
            pending = self._pending.get(key)
            if pending is None or pending.row["state"] != "pending":
                raise GatewayOperationError("PERMISSION_DENIED")
            if (pending.row["journey_ref"] != authorized.journey_ref
                    or pending.row["native_request_id"] != operation["native_request_id"]):
                raise GatewayOperationError("PERMISSION_DENIED")
            decision = self._decision(pending, operation)
            pending.row["state"] = "answered"
            pending.row["client_response_id"] = operation["client_response_id"]
            pending.decision = decision
            self._condition.notify_all()
        return {
            "schema": "flywheel.provider-session-approval-response/v1",
            "operation_ref": operation["operation_ref"],
            "request_identity": operation["request_identity"],
            "state": "answered",
            "decision": decision.behavior,
        }

    def close_operation(self, *, owner_ref: str, operation_ref: str,
                        reason: str = "operation closed") -> None:
        with self._condition:
            for key, pending in list(self._pending.items()):
                if key[0] == owner_ref and key[1] == operation_ref:
                    pending.row["state"] = "expired"
                    pending.decision = ProviderApprovalDecision(
                        "deny", key[2], reason, None)
                    self._condition.notify_all()

    def _decision(self, pending: _Pending, operation: dict) -> ProviderApprovalDecision:
        if operation["decision"] == "deny":
            if "updated_input" in operation:
                raise GatewayOperationError("PERMISSION_DENIED")
            return ProviderApprovalDecision(
                "deny", pending.row["request_identity"], "denied by operator", None)
        updated = operation.get("updated_input")
        if type(updated) is not dict or not _updated_input_allowed(pending, updated):
            raise GatewayOperationError("PERMISSION_DENIED")
        canonical_bytes(updated)
        validate_no_raw_secrets(updated)
        return ProviderApprovalDecision(
            "allow", pending.row["request_identity"], "", dict(updated))


def _updated_input_allowed(pending: _Pending, updated: dict[str, Any]) -> bool:
    scope = pending.operation.get("permission_scope")
    if type(scope) is not dict:
        return False
    policy = scope.get("approval_policy")
    if type(policy) is not dict:
        return False
    tool = pending.row["tool"]
    allowed_tools = policy.get("allow_tools")
    if type(allowed_tools) is not list or not (tool in allowed_tools or "*" in allowed_tools):
        return False
    key_map = policy.get("updated_input_keys")
    if type(key_map) is not dict:
        return False
    keys = key_map.get(tool, key_map.get("*"))
    return type(keys) is list and all(type(k) is str for k in keys) and set(updated) <= set(keys)


def _operation_ref(authorized) -> str:
    from .gateway_operation_route import operation_ref_for
    return operation_ref_for(
        authorized.owner_ref, authorized.journey_ref, authorized.client_request_id)
