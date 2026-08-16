"""Authenticated forge, recheck, and exact Plan-run orchestration."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from .evidence_json import canonical_sha256
from .evidence_public import TransportError, exact_request, parse_json
from .gateway_envelope import parse_gateway_envelope
from .gateway_grant_route import (authorize_gateway_envelope,
                                  gateway_error_response)
from .gateway_operation import GatewayOperationError, thaw_operation
from .gateway_operation_route import authorization_sha256
from .gateway_provider_adapter import ExecutionPlan, resolve_credentials
from .gateway_secret_boundary import validate_no_raw_secrets
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .plan_run_contract import (PlanRunContractError, VerifiedPlanRun,
                                build_plan_run_result)
from .plan_run_snapshot import FrozenJsonSnapshot, thaw_json
from .plan_run_store import (PlanRunStoreError, commit_plan_result,
    load_plan_prp, load_plan_result, plan_run_lock_path, seal_plan_prp,
    verify_plan_run)
from .plan_workflow_contract import validate_plan_workflow_run
from .workflows import run_workflow

_FORGE_FIELDS = {"goal", "examples", "documentation", "context",
                 "intent_source", "architecture_source", "task_type",
                 "success_criterion"}


def plan_run_ref_for(owner_ref: str, journey_ref: str,
                     client_request_id: str) -> str:
    digest = canonical_sha256({"owner_ref": owner_ref,
        "journey_ref": journey_ref, "client_request_id": client_request_id})
    return f"plr_{digest[:32]}"


def _text(value: object, *, allow_empty: bool = True) -> bool:
    return (type(value) is str and (allow_empty or bool(value.strip())))


def _strings(value: object) -> bool:
    return type(value) is list and all(_text(item, allow_empty=False)
                                       for item in value)


def _forge(body: dict, owner_ref: str, state_root: Path,
           clock: Callable[[], str]) -> dict:
    exact_request(body, _FORGE_FIELDS, optional=_FORGE_FIELDS - {"goal"})
    if (not _text(body.get("goal"), allow_empty=False)
            or any(name in body and not _text(body[name]) for name in (
                "context", "intent_source", "architecture_source",
                "task_type", "success_criterion"))
            or any(name in body and not _strings(body[name])
                   for name in ("examples", "documentation"))):
        raise GatewayOperationError("INVALID_REQUEST")
    validate_no_raw_secrets(body)
    from .context_forge import forge_prp
    prp = forge_prp(body["goal"].strip(),
        examples=body.get("examples"), documentation=body.get("documentation"),
        context=body.get("context", ""), task_type=body.get("task_type") or None,
        success_criterion=body.get("success_criterion", ""),
        intent_source=body.get("intent_source", ""),
        architecture_source=body.get("architecture_source", "")).to_dict()
    return seal_plan_prp(prp, owner_ref=owner_ref, state_root=state_root,
                         clock=clock).to_dict()


def _recheck(body: dict, owner_ref: str, state_root: Path) -> dict:
    exact_request(body, {"prp_id", "intent_source", "architecture_source"},
                  optional={"intent_source", "architecture_source"})
    if (not _text(body.get("prp_id"), allow_empty=False)
            or any(name in body and not _text(body[name], allow_empty=False)
                   for name in ("intent_source", "architecture_source"))):
        raise GatewayOperationError("INVALID_REQUEST")
    validate_no_raw_secrets(body)
    record = load_plan_prp(body["prp_id"], owner_ref=owner_ref,
                           state_root=state_root)
    arms = {}
    for arm in ("intent", "architecture"):
        sealed, source = record.prp[f"{arm}_sha256"], body.get(f"{arm}_source")
        if sealed and source is not None:
            current = hashlib.sha256(source.encode("utf-8")).hexdigest()
            arms[arm] = {"sealed_sha256": sealed, "current_sha256": current,
                         "moved": current != sealed}
    if not arms:
        raise GatewayOperationError("INVALID_REQUEST")
    output = {"schema": "flywheel.plan-forge-recheck/v1",
        "prp_id": record.prp_id, "seal_sha256": record.seal_sha256,
        "arms": arms}
    hashes = [value["current_sha256"] for value in arms.values()]
    if len(hashes) == 2 and hashes[0] == hashes[1]:
        output["degenerate"] = True
        output["note"] = "identical arms do not provide an independent drift check"
    else:
        output["any_moved"] = any(value["moved"] for value in arms.values())
    return output


def _replay_matches(result: dict, envelope) -> bool:
    receipt, operation = result["receipt"], envelope.operation
    value = thaw_operation(operation.operation)
    binding, workflow = value["binding"], result["workflow_run"]
    return (receipt["journey_ref"] == envelope.journey_ref
        and receipt["expected_event_head"] == envelope.expected_event_head
        and receipt["client_request_id"] == envelope.client_request_id
        and receipt["operation_sha256"] == operation.operation_sha256
        and receipt["arguments_sha256"] == operation.arguments_sha256
        and receipt["grant_ref_sha256"] == canonical_sha256(envelope.grant_ref)
        and receipt["binding"] == binding
        and receipt["workflow"] == value["workflow"]
        and receipt["endpoint"] == value["endpoint"]
        and workflow["workflow"] == value["workflow"]
        and workflow["endpoint"] == value["endpoint"])


def _secret_echo(value: object, bindings: object) -> bool:
    secrets = getattr(bindings, "_values", {})
    needles = tuple(item for item in getattr(secrets, "values", lambda: ())()
                    if type(item) is str and item)
    if not needles:
        return False
    def visit(item: object) -> bool:
        if type(item) is str:
            return any(secret in item for secret in needles)
        if type(item) is list:
            return any(visit(child) for child in item)
        if type(item) is dict:
            return any(visit(key) or visit(child) for key, child in item.items())
        return False
    return visit(value)


def _dispatch_inputs(authorized):
    plan = authorized.execution_plan
    if (not isinstance(plan, ExecutionPlan)
            or not isinstance(plan.verified_plan, VerifiedPlanRun)
            or not isinstance(plan.workflow_snapshot, FrozenJsonSnapshot)
            or not isinstance(plan.profile_snapshot, FrozenJsonSnapshot)
            or plan.workflow_sha256 != plan.workflow_snapshot.sha256
            or plan.profile_sha256 != plan.profile_snapshot.sha256):
        raise GatewayOperationError("PERMISSION_DENIED")
    operation = thaw_operation(authorized.operation)
    verified = plan.verified_plan
    try:
        profile = thaw_json(plan.profile_snapshot)
        prp = verified.record.prp
        if (profile.get("workflow") != operation["workflow"]
                or type(profile.get("system", "")) is not str
                or prp != verified.binding.prp):
            raise ValueError
    except Exception:
        raise GatewayOperationError("PERMISSION_DENIED") from None
    system = verified.binding.prompt
    if profile.get("system"):
        system += "\n\n" + profile["system"]
    return plan, operation, prp["goal"], system


def _dispatch(authorized, root: Path, run_root, countersign) -> dict:
    plan, operation, goal, system = _dispatch_inputs(authorized)
    verified = plan.verified_plan
    try:
        returned = run_workflow(operation["workflow"], goal, operation["endpoint"],
            root=str(root), workflow_snapshot=plan.workflow_snapshot.canonical,
            allow_write=operation["allow_write"], allow_exec=operation["allow_exec"],
            allow_mcp=False, test_cmd=operation.get("test_cmd"), system=system,
            run_root=None, credential_bindings=authorized.credential_bindings,
            authorized=True)
        workflow = validate_plan_workflow_run(returned,
            workflow=operation["workflow"], endpoint=operation["endpoint"],
            require_countersign=False)
    except Exception:
        raise GatewayOperationError("EXTERNAL_ACTION_FAILED") from None
    if _secret_echo(workflow, authorized.credential_bindings):
        raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
    try:
        before_countersign = canonical_sha256(workflow)
        witness = countersign(workflow)
        if (canonical_sha256(workflow) != before_countersign
                or type(witness) is not dict):
            raise ValueError
        workflow["run_countersign"] = witness
        return build_plan_run_result(workflow_run=workflow,
            workflow=operation["workflow"], endpoint=operation["endpoint"],
            plan_run_ref=plan_run_ref_for(authorized.owner_ref,
                authorized.journey_ref, authorized.client_request_id),
            binding=verified.binding, journey_ref=authorized.journey_ref,
            expected_event_head=authorized.expected_event_head,
            client_request_id=authorized.client_request_id,
            operation_sha256=authorized.operation_sha256,
            arguments_sha256=authorized.arguments_sha256,
            authorization_sha256=authorization_sha256(authorized),
            grant_ref_sha256=canonical_sha256(authorized.grant_ref),
            execution_plan_sha256=plan.digest,
            workflow_sha256=plan.workflow_sha256,
            profile_sha256=plan.profile_sha256,
            effective_system_sha256=hashlib.sha256(system.encode("utf-8")).hexdigest())
    except GatewayOperationError:
        raise
    except Exception:
        raise PlanRunStoreError() from None


def _run(envelope, *, owner_ref: str, state_root: Path, default_root: Path,
         run_root, clock, resolve_root, countersign) -> dict:
    ref = plan_run_ref_for(owner_ref, envelope.journey_ref,
                           envelope.client_request_id)
    lock_path = plan_run_lock_path(state_root, owner_ref, ref)
    with ExclusiveJourneyLock.acquire(lock_path):
        operation = thaw_operation(envelope.operation.operation)
        prior = load_plan_result(ref, owner_ref=owner_ref, state_root=state_root)
        if prior is not None:
            if _replay_matches(prior, envelope):
                return prior
            raise GatewayOperationError("IDEMPOTENCY_MISMATCH")
        verify_plan_run(operation["binding"], owner_ref=owner_ref,
                        state_root=state_root)
        try:
            root, refusal = resolve_root(operation["root"], default_root)
        except Exception:
            raise GatewayOperationError("INVALID_REQUEST") from None
        if refusal or not isinstance(root, Path):
            raise GatewayOperationError("INVALID_REQUEST")
        authorized = authorize_gateway_envelope(
            envelope, owner_ref=owner_ref, state_root=state_root, clock=clock)
        authorized = resolve_credentials(authorized, state_root)
        result = _dispatch(authorized, root, run_root, countersign)
        return commit_plan_result(result, owner_ref=owner_ref,
                                  state_root=state_root)


def plan_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path,
              default_root: Path, run_root, clock: Callable[[], str],
              resolve_root: Callable, countersign: Callable | None = None
              ) -> tuple[dict, int]:
    """Handle one authenticated Plan endpoint without starting any service."""
    try:
        if path == "/api/plan/forge":
            return _forge(parse_json(raw), owner_ref, state_root, clock), 200
        if path == "/api/plan/forge/recheck":
            return _recheck(parse_json(raw), owner_ref, state_root), 200
        if path != "/api/plan/run" or countersign is None:
            raise GatewayOperationError("NOT_FOUND")
        envelope = parse_gateway_envelope("plan.run", raw)
        return _run(envelope, owner_ref=owner_ref, state_root=state_root,
            default_root=default_root, run_root=run_root, clock=clock,
            resolve_root=resolve_root, countersign=countersign), 200
    except (TransportError, GatewayOperationError, PlanRunContractError,
            PlanRunStoreError, JourneyLockBusy, OSError, TypeError,
            ValueError) as exc:
        return gateway_error_response(exc)
