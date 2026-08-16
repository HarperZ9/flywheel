"""Fixed public failures for authorized external-action adapters."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .credential_handles import CredentialHandleStore
from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError


_LOCAL_MODELS = frozenset((
    "", "flywheel", "flywheel-serve", "serve", "default", "local", "auto",
))


@dataclass(frozen=True)
class ExecutionPlan:
    digest: str
    required_slots: tuple[str, ...]
    credential_refs: tuple[str, ...]
    launch: object | None = None
    plugin_kind: str | None = None
    marketplace: object | None = None
    workflow_sha256: str | None = None
    profile_sha256: str | None = None
    profile_system: str = field(default="", repr=False)
    verified_plan: object | None = field(default=None, repr=False)


def freeze_execution_plan(operation, *, owner_ref: str | None = None,
                          state_root: Path | None = None) -> ExecutionPlan:
    """Snapshot server-derived dispatch metadata before approval."""
    launch = kind = market = None
    workflow_sha = profile_sha = None
    system, verified = "", None
    if operation.action in {"plugin.probe", "plugin.call"}:
        from .plugins import plugin_execution_plan
        launch, kind, required, refs = plugin_execution_plan(
            operation.operation["name"])
    elif operation.action == "marketplace.install":
        from .marketplace import marketplace_execution_plan
        market = marketplace_execution_plan(operation.operation["name"])
        required, refs = market.required_slots, market.credential_refs
    elif operation.action == "plan.run":
        workflow_sha, profile_sha, system, verified = _plan_snapshot(
            operation, owner_ref, state_root)
        required, refs = _credential_plan(operation)
    else:
        required, refs = _credential_plan(operation)
        workflow_sha = profile_sha = None
        system, verified = "", None
    argv = tuple(launch.argv) if hasattr(launch, "argv") else (
        tuple(launch) if launch is not None else ())
    cwd = getattr(launch, "cwd", None)
    market_value = (None if market is None else {
        "name": market.name, "command": list(market.command),
        "detail": market.detail, "required_slots": list(market.required_slots),
        "credential_refs": list(market.credential_refs)})
    digest = canonical_sha256({
        "action": operation.action, "operation_sha256": operation.operation_sha256,
        "required_slots": list(required), "credential_refs": list(refs),
        "plugin_kind": kind, "argv": list(argv), "cwd": cwd,
        "marketplace": market_value, "workflow_sha256": workflow_sha,
        "profile_sha256": profile_sha})
    return ExecutionPlan(
        digest, tuple(required), tuple(refs), launch, kind, market,
        workflow_sha, profile_sha, system, verified)


def _plan_snapshot(operation, owner_ref, state_root):
    try:
        from .plan_run_store import verify_plan_run
        from .profiles import get_profile
        from .workflows import WORKFLOWS
        from .gateway_operation import thaw_operation
        if type(owner_ref) is not str or state_root is None:
            raise ValueError
        value = operation.operation
        profile = get_profile(value["profile"])
        workflow = WORKFLOWS.get(value["workflow"])
        if (type(profile) is not dict or type(workflow) is not dict
                or profile.get("workflow") != value["workflow"]
                or type(profile.get("system", "")) is not str):
            raise GatewayOperationError("INVALID_REQUEST")
        verified = verify_plan_run(thaw_operation(value)["binding"],
            owner_ref=owner_ref, state_root=state_root)
        workflow_value = {"name": value["workflow"], **workflow}
        return (canonical_sha256(workflow_value), canonical_sha256(profile),
                profile.get("system", ""), verified)
    except GatewayOperationError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "PLAN_BINDING_DRIFT")
        raise GatewayOperationError(code) from None


def _credential_plan(operation) -> tuple[tuple[str, ...], tuple[str, ...]]:
    value, action = operation.operation, operation.action
    if action == "chat.complete":
        name = value["model"].split(":", 1)[0]
        if name in _LOCAL_MODELS:
            return (), ()
        from .endpoint_registry import credential_slots_for_endpoint
        return credential_slots_for_endpoint(name), ()
    if action in {"agent.run", "workflow.run", "plan.run"}:
        from .endpoint_registry import credential_slots_for_endpoint
        return credential_slots_for_endpoint(value["endpoint"]), ()
    if action in {"plugin.probe", "plugin.call"}:
        from .plugins import plugin_credentials
        return plugin_credentials(value["name"])
    if action == "plugin.register":
        return tuple(value["requires"]), ()
    if action in {"marketplace.install", "marketplace.remove"}:
        from .marketplace import marketplace_credentials
        return marketplace_credentials(value["name"])
    if action == "marketplace.add":
        return tuple(value["requires"]), ()
    return (), ()


def credential_slots(operation, owner_ref: str, state_root: Path,
                     plan: ExecutionPlan | None = None) -> tuple[str, ...]:
    """Validate owner handle metadata against the server-derived frozen plan."""
    try:
        plan = plan or freeze_execution_plan(operation)
        required, frozen_refs = plan.required_slots, plan.credential_refs
        refs = operation.credential_refs
        store = CredentialHandleStore(
            state_root, keychain_get=lambda _slot: None)
        actual = store.slot_names_exact(owner_ref, refs)
        if actual != required or frozen_refs and tuple(refs) != frozen_refs:
            raise GatewayOperationError("PERMISSION_REQUIRED")
        return required
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError("PERMISSION_REQUIRED") from None


def resolve_credentials(operation, state_root: Path):
    """Resolve exact handle values only after grant consumption."""
    plan = operation.execution_plan
    if not isinstance(plan, ExecutionPlan):
        raise GatewayOperationError("PERMISSION_REQUIRED")
    required = credential_slots(
        operation, operation.owner_ref, state_root, plan=plan)
    try:
        from .keychain import keychain_get
        bindings = CredentialHandleStore(
            state_root, keychain_get=keychain_get).resolve_exact(
                operation.owner_ref, operation.credential_refs, required)
        if plan.launch is not None:
            from .plugins import _restricted_launch
            plan = replace(
                plan, launch=_restricted_launch(plan.launch, bindings, required))
        return replace(operation, credential_bindings=bindings,
                       execution_plan=plan)
    except Exception:
        raise GatewayOperationError("PERMISSION_REQUIRED") from None


def fixed_external_failure() -> tuple[dict, int]:
    """Return the only public envelope for a failed external action."""
    return ({
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {
            "code": "EXTERNAL_ACTION_FAILED",
            "message": "authorized external action failed",
        },
    }, 502)
