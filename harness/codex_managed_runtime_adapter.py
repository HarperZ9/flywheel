"""Managed Codex provider-session admission and lazy adapter glue."""
from __future__ import annotations

from .codex_provider_session import CodexProviderSessionAdapter
from .evidence_json import canonical_sha256
from .gateway_operation import thaw_operation
from .provider_session_contract import (
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
    ProviderSessionError,
)


class ManagedCodexRuntimeRegistry:
    def __init__(self, composition) -> None:
        self.composition = composition

    def binding_snapshot(self, *, owner_ref: str, journey_ref: str,
                         expected_event_head: str, operation: dict, **_) -> dict:
        reason = self._cheap_hold_reason(operation)
        if reason is not None:
            return self._held_snapshot(owner_ref, journey_ref, expected_event_head,
                                       operation, reason)
        session = inventory = manifest = binding = None
        held_reason = None
        try:
            session, _profile, inventory, manifest = self._acquire(owner_ref)
            binding = self._runtime_binding(
                owner_ref, journey_ref, expected_event_head, operation,
                session=session, inventory=inventory, manifest=manifest)
        except Exception as exc:
            held_reason = _reason_from_exception(exc)
        if session is not None and not self._close(session):
            return self._held_snapshot(owner_ref, journey_ref, expected_event_head,
                                       operation, "AGENT_NATIVE_CLEANUP_REQUIRED")
        if held_reason is not None:
            return self._held_snapshot(owner_ref, journey_ref, expected_event_head,
                                       operation, held_reason)
        return self._snapshot(
            owner_ref, journey_ref, expected_event_head, operation,
            binding=binding, inventory=inventory, admitted=True,
            reason="admitted", limitations=[],
            runtime_kind="codex-managed-owned-authenticated")

    def adapter_for(self, *, authorized, operation_ref):
        try:
            operation = thaw_operation(authorized.operation)
            if self._cheap_hold_reason(operation) is not None:
                return None
            return _ManagedCodexProviderSessionAdapter(
                self, owner_ref=authorized.owner_ref,
                journey_ref=authorized.journey_ref,
                expected_event_head=authorized.expected_event_head,
                operation=operation, operation_ref=operation_ref)
        except Exception:
            return None

    def _cheap_hold_reason(self, operation: dict) -> str | None:
        config = self.composition.config
        if self.composition.disabled_reason:
            return self.composition.disabled_reason
        if config is None:
            return "AGENT_NATIVE_RUNTIME_DISABLED"
        if operation.get("provider") != "codex":
            return "AGENT_BINDING_DRIFT"
        if operation.get("workspace_ref") != self.composition.workspace.workspace_ref:
            return "AGENT_BINDING_DRIFT"
        if operation.get("model") and operation.get("model") != config.model:
            return "AGENT_BINDING_DRIFT"
        if self.composition.lifecycle is None:
            return "AGENT_NATIVE_BASELINE_PENDING"
        return None

    def _acquire(self, owner_ref: str):
        return self.composition.lifecycle.runtime_session_for_owner(
            owner_ref=owner_ref)

    def _close(self, session) -> bool:
        close = getattr(self.composition.lifecycle, "_close_and_release", None)
        if callable(close):
            return close(session)
        try:
            return session.close() is True
        except Exception:
            return False

    def _runtime_binding(self, owner_ref: str, journey_ref: str,
                         expected_event_head: str, operation: dict, *,
                         session, inventory, manifest) -> ProviderRuntimeBinding:
        config_digest = _text(getattr(session, "config_digest", ""))
        if config_digest is None:
            raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
        return ProviderRuntimeBinding(
            "codex", self.composition.workspace.workspace_ref, config_digest,
            self._capability_digest(
                owner_ref, journey_ref, expected_event_head, operation,
                config_digest=config_digest, inventory=inventory,
                manifest=manifest))

    def _capability_digest(self, owner_ref: str, journey_ref: str,
                           expected_event_head: str, operation: dict, *,
                           config_digest: str, inventory, manifest) -> str:
        config = self.composition.config
        auth = manifest.get("auth_extension") if isinstance(manifest, dict) else {}
        return "codex-managed:" + canonical_sha256({
            "schema": "flywheel.codex-managed-runtime-capability/v1",
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "event_head": expected_event_head,
            "provider": "codex",
            "workspace_ref": self.composition.workspace.workspace_ref,
            "workspace_identity": self.composition.workspace.identity,
            "model": operation.get("model") or config.model,
            "permission_scope_sha256": canonical_sha256(
                operation.get("permission_scope", {})),
            "executable_sha256": config.executable_sha256,
            "codex_version": config.codex_version,
            "version_provenance": config.version_provenance,
            "inventory_sha256": getattr(inventory, "sha256", ""),
            "auth_extension": {
                "present": True,
                "schema": auth.get("schema"),
                "content_read": auth.get("content_read"),
                "exact_paths_only": auth.get("exact_paths_only"),
            },
            "runtime_policy": {
                "approval_policy": "on-request",
                "approvals_reviewer": "user",
                "sandbox_mode": "read-only",
                "web_search": "disabled",
                "network_access": False,
            },
            "config_digest": config_digest,
        })

    def _held_snapshot(self, owner_ref: str, journey_ref: str,
                       expected_event_head: str, operation: dict,
                       reason: str) -> dict:
        material = {
            "schema": "flywheel.codex-managed-runtime-hold/v1",
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "event_head": expected_event_head,
            "operation": _operation_material(operation),
            "workspace_ref": self.composition.workspace.workspace_ref,
            "config": (self.composition.config.as_digest_material()
                       if self.composition.config else None),
            "reason": reason,
        }
        binding = ProviderRuntimeBinding(
            str(operation.get("provider", "")),
            str(operation.get("workspace_ref", "")),
            "codex-managed:" + canonical_sha256(material),
            "codex-managed:" + canonical_sha256({**material, "capability": False}))
        return self._snapshot(
            owner_ref, journey_ref, expected_event_head, operation,
            binding=binding, inventory=None, admitted=False, reason=reason,
            limitations=["codex managed runtime admission is held"],
            runtime_kind="codex-managed-owned-held")

    def _snapshot(self, owner_ref: str, journey_ref: str,
                  expected_event_head: str, operation: dict, *, binding,
                  inventory, admitted: bool, reason: str,
                  limitations: list[str], runtime_kind: str) -> dict:
        material = {
            "schema": "flywheel.codex-managed-runtime-binding/v1",
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "event_head": expected_event_head,
            "operation": _operation_material(operation),
            "config_digest": binding.config_digest,
            "capability_digest": binding.capability_digest,
            "inventory_sha256": getattr(inventory, "sha256", ""),
            "admitted": admitted,
            "reason": reason,
        }
        return {
            "schema": "flywheel.provider-session-runtime-binding/v1",
            "provider": str(operation.get("provider", "")),
            "owner_ref": owner_ref,
            "journey_ref": journey_ref,
            "workspace_ref": str(operation.get(
                "workspace_ref", self.composition.workspace.workspace_ref)),
            "model": str(operation.get("model") or (
                self.composition.config.model if self.composition.config else "")),
            "permission_scope_sha256": canonical_sha256(
                operation.get("permission_scope", {})),
            "config_digest": binding.config_digest,
            "capability_digest": binding.capability_digest,
            "provider_binding_ref": "psb_" + canonical_sha256(material)[:32],
            "admitted": admitted,
            "reason": reason,
            "limitations": limitations,
            "runtime_kind": runtime_kind,
            "observed_at_event_head": expected_event_head,
        }


class _ManagedCodexProviderSessionAdapter:
    provider = "codex"

    def __init__(self, registry: ManagedCodexRuntimeRegistry, *, owner_ref: str,
                 journey_ref: str, expected_event_head: str,
                 operation: dict, operation_ref: str) -> None:
        self.registry = registry
        self.owner_ref = owner_ref
        self.journey_ref = journey_ref
        self.expected_event_head = expected_event_head
        self.operation = dict(operation)
        self.operation_ref = operation_ref

    def current_binding(self) -> ProviderRuntimeBinding:
        session, inventory, manifest = self._acquire_runtime()
        try:
            return self.registry._runtime_binding(
                self.owner_ref, self.journey_ref, self.expected_event_head,
                self.operation, session=session, inventory=inventory,
                manifest=manifest)
        finally:
            if not self.registry._close(session):
                raise ProviderSessionError("AGENT_NATIVE_CLEANUP_REQUIRED")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        return self._with_runtime(lambda adapter: adapter.start_turn(
            request, emit=emit, request_approval=request_approval,
            cancelled=cancelled))

    def resume(self, request, *, emit):
        return self._with_runtime(lambda adapter: adapter.resume(
            request, emit=emit))

    def reconcile(self, request, *, emit):
        return self._with_runtime(lambda adapter: adapter.reconcile(
            request, emit=emit))

    def _with_runtime(self, call):
        session = outcome = None
        try:
            session, inventory, manifest = self._acquire_runtime()
            binding = self.registry._runtime_binding(
                self.owner_ref, self.journey_ref, self.expected_event_head,
                self.operation, session=session, inventory=inventory,
                manifest=manifest)
            adapter = CodexProviderSessionAdapter(
                client_supplier=lambda: session.client,
                transport_supplier=lambda: session.transport,
                runtime_binding_supplier=lambda: binding)
            outcome = call(adapter)
        except ProviderSessionError as exc:
            outcome = ProviderOperationOutcome.failed(exc.code, **exc.detail)
        finally:
            if session is not None and not self.registry._close(session):
                return _cleanup_failure(outcome)
        return outcome

    def _acquire_runtime(self):
        session, _profile, inventory, manifest = self.registry._acquire(
            self.owner_ref)
        return session, inventory, manifest


def _cleanup_failure(outcome) -> ProviderOperationOutcome:
    result = getattr(outcome, "result", {}) if outcome is not None else {}
    provider_session = result.get("provider_session") if isinstance(result, dict) else None
    payload = {
        "history_status": "indeterminate",
        "side_effect_status": "indeterminate",
    }
    if isinstance(provider_session, dict):
        payload["provider_session"] = provider_session
    return ProviderOperationOutcome.failed("AGENT_NATIVE_CLEANUP_REQUIRED", **payload)


def _reason_from_exception(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "")
    if code in {"AGENT_NATIVE_AUTH_REQUIRED",
                "BASELINE_ACCEPTED_INVENTORY_REQUIRED",
                "BASELINE_INVENTORY_AMBIGUOUS",
                "BASELINE_INVENTORY_REJECTED"}:
        return "AGENT_NATIVE_AUTH_REQUIRED"
    if code in {"AGENT_NATIVE_CLEANUP_REQUIRED", "BASELINE_CLEANUP_REQUIRED"}:
        return "AGENT_NATIVE_CLEANUP_REQUIRED"
    if code.startswith("AGENT_") or code == "MODEL_SELECTION_REQUIRED":
        return code
    return "AGENT_NATIVE_RUNTIME_DISABLED"


def _operation_material(operation: dict) -> dict:
    return {
        "provider": str(operation.get("provider", "")),
        "workspace_ref": str(operation.get("workspace_ref", "")),
        "model": str(operation.get("model", "")),
        "permission_scope_sha256": canonical_sha256(
            operation.get("permission_scope", {})),
    }


def _text(value: object) -> str | None:
    return value if type(value) is str and value.strip() else None
