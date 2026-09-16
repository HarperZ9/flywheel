"""Gateway-owned v2 child routes for subagent swarms."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256
from .gateway_operation import (AuthorizedOperation, GatewayOperationError,
    canonicalize_operation, thaw_operation)
from .gateway_operation_route import (authorization_sha256, operation_ref_for)
from .gateway_provider_adapter import (credential_slots, freeze_execution_plan)
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN
from .operation_grants import OWNER_REF_PATTERN, _secure_owner_only
from .plan_run_snapshot import thaw_json
from .subagent_roles import validate_child
from .subagent_gateway_contract import (PARENT_AUTHORITY_SCHEMA,
    RESERVATION_SCHEMA, ROUTING_SCHEMA_V2, SPAWN_SCHEMA_V2, SPEC_SCHEMA_V2,
    route_summary)
from .subagent_gateway_validate import (bounded_int, bounded_time,
    child_caps_within_parent, is_v2_child, operation_for_child,
    preflight_child_credentials, sealed_route)

def _refuse(message: str) -> None:
    raise ValueError(message)


def _parent_raw(value: object) -> bytes:
    if not isinstance(value, dict):
        _refuse("parent authority must be a gateway authorization envelope")
    return canonical_bytes(value)

def preview_parent_authority(raw: object, *, owner_ref: str, state_root: Path,
                             workspace_root: Path | None) -> dict:
    from .gateway_envelope import parse_gateway_envelope
    env = parse_gateway_envelope("agent.run", _parent_raw(raw))
    plan = freeze_execution_plan(env.operation, owner_ref=owner_ref,
        state_root=state_root, workspace_root=workspace_root)
    binding = thaw_json(plan.agent_binding)
    return _parent_summary(owner_ref, env.journey_ref, env.client_request_id,
        env.grant_ref, env.operation.operation_sha256, plan.agent_binding.sha256,
        "", binding)

def authorize_parent_authority(raw: object, service, *, owner_ref: str,
                               workspace_root: Path | None):
    kwargs = {}
    if getattr(service.authorizer, "__module__", "") == "harness.gateway_grant_route":
        kwargs["workspace_root"] = workspace_root
    authorized = service.authorizer("agent.run", _parent_raw(raw),
        owner_ref=owner_ref, state_root=service.state_root,
        clock=service.clock, **kwargs)
    return service.credential_resolver(authorized, service.state_root)

def require_authorized_parent(value: object) -> AuthorizedOperation:
    if not isinstance(value, AuthorizedOperation) or value.action != "agent.run" \
            or getattr(value.execution_plan, "agent_binding", None) is None:
        _refuse("parent authority must be an authorized gateway operation")
    return value

def parent_authority_summary(value: AuthorizedOperation) -> dict:
    parent = require_authorized_parent(value)
    binding = thaw_json(parent.execution_plan.agent_binding)
    return _parent_summary(parent.owner_ref, parent.journey_ref,
        parent.client_request_id, parent.grant_ref, parent.operation_sha256,
        parent.execution_plan.agent_binding.sha256,
        authorization_sha256(parent), binding)

def _parent_summary(owner, journey, request, grant, op_sha, binding_sha,
                    auth_sha, binding) -> dict:
    return {"schema": PARENT_AUTHORITY_SCHEMA, "owner_ref": owner,
        "journey_ref": journey, "client_request_id": request,
        "operation_ref": operation_ref_for(owner, journey, request),
        "operation_sha256": op_sha, "agent_binding_sha256": binding_sha,
        "authorization_sha256": auth_sha,
        "capabilities": {"allow_write": binding["capabilities"]["allow_write"],
            "allow_exec": binding["capabilities"]["allow_exec"]},
        "budget": dict(binding["budget"])}

def validate_parent_authority(value: object) -> dict:
    fields = {"schema", "owner_ref", "journey_ref", "client_request_id",
        "operation_ref", "operation_sha256", "agent_binding_sha256",
        "authorization_sha256", "capabilities", "budget"}
    if not isinstance(value, dict) or set(value) != fields \
            or value.get("schema") != PARENT_AUTHORITY_SCHEMA:
        _refuse("parent authority is invalid")
    if (OWNER_REF_PATTERN.fullmatch(value["owner_ref"]) is None
            or JOURNEY_REF_PATTERN.fullmatch(value["journey_ref"]) is None
            or not isinstance(value["client_request_id"], str)
            or operation_ref_for(value["owner_ref"], value["journey_ref"],
                value["client_request_id"]) != value["operation_ref"]
            or any(SHA256_PATTERN.fullmatch(value[k]) is None for k in (
                "operation_sha256", "agent_binding_sha256"))
            or value["authorization_sha256"] and
                SHA256_PATTERN.fullmatch(value["authorization_sha256"]) is None):
        _refuse("parent authority identity is invalid")
    caps, budget = value["capabilities"], value["budget"]
    if not isinstance(caps, dict) or set(caps) != {"allow_write", "allow_exec"} \
            or type(caps["allow_write"]) is not bool \
            or type(caps["allow_exec"]) is not bool:
        _refuse("parent authority capabilities are invalid")
    if not isinstance(budget, dict) or set(budget) != {
            "max_steps", "max_tokens", "timeout_s"}:
        _refuse("parent authority budget is invalid")
    bounded_int(budget["max_steps"], 1, 12, "parent authority max_steps")
    if budget["max_tokens"] is not None:
        bounded_int(budget["max_tokens"], 1, 32768, "parent authority max_tokens")
    bounded_time(budget["timeout_s"], 1, 1800, "parent authority timeout_s")
    return {**value, "capabilities": dict(caps), "budget": dict(budget)}

def aggregate_child_budget(children: list[dict], parent: dict,
                           swarm_timeout: float) -> dict:
    parent = validate_parent_authority(parent)
    totals = {"max_steps": 0, "max_tokens": 0, "timeout_s": 0.0}
    for child in children:
        sealed, route = sealed_route(child, parent)
        totals["max_steps"] += route["max_steps"]
        totals["max_tokens"] += route["max_tokens"]
        totals["timeout_s"] += float(route["timeout_s"])
        child_caps_within_parent(sealed, parent)
    if totals["max_steps"] > parent["budget"]["max_steps"]:
        _refuse("aggregate child steps exceed parent authority")
    cap = parent["budget"]["max_tokens"]
    if cap is not None and totals["max_tokens"] > cap:
        _refuse("aggregate child tokens exceed parent authority")
    if (totals["timeout_s"] > float(parent["budget"]["timeout_s"])
            or float(swarm_timeout) > float(parent["budget"]["timeout_s"])):
        _refuse("aggregate child timeout exceeds parent authority")
    totals["timeout_s"] = int(totals["timeout_s"])
    return totals


@contextmanager
def parent_spawn_guard(state_root: Path, owner_ref: str):
    root = Path(state_root) / "gateway-subagents" / "v1" / "owners"
    owner = root / owner_ref
    try:
        root.mkdir(parents=True, exist_ok=True); _secure_owner_only(root, directory=True)
        owner.mkdir(exist_ok=True); _secure_owner_only(owner, directory=True)
    except JourneyLockBusy:
        raise GatewayOperationError("STORE_BUSY") from None
    except Exception:
        raise GatewayOperationError("PERMISSION_DENIED") from None
    try:
        with ExclusiveJourneyLock.acquire(owner / ".lock"):
            yield
    except JourneyLockBusy:
        raise GatewayOperationError("STORE_BUSY") from None


def reserve_gateway_swarm(service, parent_auth: AuthorizedOperation,
                          swarm_id: str, specs: list[dict],
                          totals: dict, timeout_s: float) -> dict:
    parent = parent_authority_summary(parent_auth)
    payload = {"schema": RESERVATION_SCHEMA, "swarm_id": swarm_id,
        "parent_operation_ref": parent["operation_ref"],
        "parent_authorization_sha256": parent["authorization_sha256"],
        "budget": totals, "timeout_s": float(timeout_s),
        "child_operation_refs": [spec["operation_ref"] for spec in specs],
        "child_operation_sha256": [spec["operation_sha256"] for spec in specs]}
    journey = service._journey(parent["owner_ref"])
    head = journey.resume(parent["journey_ref"])["event_head_sha256"]
    ack = journey._append_lifecycle(journey_ref=parent["journey_ref"],
        expected_event_head=head,
        client_request_id=_short_id(parent["client_request_id"], swarm_id, "reserve"),
        operation="record_receipt", payload=payload)
    return {**payload, "event_sha256": ack.event_sha256,
            "event_head_sha256": ack.event_head_sha256}


def attach_reservation(spec: dict, reservation: dict) -> dict:
    value = {**spec, "aggregate_reservation": reservation}
    value.pop("spec_sha256", None); value["spec_sha256"] = canonical_sha256(value)
    return value


def build_bound_spec(*, swarm_id: str, child_id: str, goal: str, child: dict,
                     workspace: Path, created_at: str, parent_authority: dict,
                     workspace_root: Path | None = None,
                     state_root: Path | None = None) -> dict:
    parent = validate_parent_authority(parent_authority)
    sealed, route = sealed_route(child, parent)
    operation = operation_for_child(goal, sealed, route, workspace)
    canonical = canonicalize_operation("agent.run", operation)
    plan = freeze_execution_plan(canonical, owner_ref=parent["owner_ref"],
        state_root=state_root, workspace_root=workspace_root or workspace)
    if state_root is not None:
        credential_slots(canonical, parent["owner_ref"], state_root, plan=plan)
    binding = thaw_json(plan.agent_binding)
    request_id = _short_id(parent["client_request_id"], child_id,
        canonical.operation_sha256)
    spec = {"schema": SPEC_SCHEMA_V2, "swarm_id": swarm_id,
        "child_id": child_id, "role": sealed["role"], "prompt": sealed["prompt"],
        "goal": goal, "workspace": str(workspace), "created_at": created_at,
        "allow_write": sealed["allow_write"], "allow_exec": sealed["allow_exec"],
        "client_request_id": request_id,
        "operation_ref": operation_ref_for(parent["owner_ref"],
            parent["journey_ref"], request_id),
        "operation": thaw_operation(canonical.operation),
        "operation_sha256": canonical.operation_sha256,
        "agent_binding": binding, "agent_binding_sha256": plan.agent_binding.sha256,
        "execution_plan_sha256": plan.digest,
        "required_slots": list(plan.required_slots),
        "parent_authority": parent,
        "route": route_summary(binding, canonical.operation_sha256)}
    spec["spec_sha256"] = canonical_sha256(spec)
    return spec


def validate_bound_spec(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema") != SPEC_SCHEMA_V2:
        _refuse("the file is not a v2 subagent spec")
    digest = data.get("spec_sha256", "")
    body = {k: v for k, v in data.items() if k != "spec_sha256"}
    if not isinstance(digest, str) or canonical_sha256(body) != digest:
        _refuse("the spec seal does not match its content")
    parent = validate_parent_authority(data.get("parent_authority"))
    validate_child(str(data.get("role")), str(data.get("prompt") or ""),
        allow_write=bool(data.get("allow_write")), allow_exec=bool(data.get("allow_exec")))
    child_caps_within_parent(data, parent)
    canonical = canonicalize_operation("agent.run", data.get("operation"))
    from .gateway_agent_binding import validate_agent_binding
    validate_agent_binding(data.get("agent_binding"), canonical)
    if (canonical.operation_sha256 != data.get("operation_sha256")
            or canonical_sha256(data.get("agent_binding")) != data.get("agent_binding_sha256")
            or data.get("route") != route_summary(data["agent_binding"],
                canonical.operation_sha256)
            or data.get("operation_ref") != operation_ref_for(parent["owner_ref"],
                parent["journey_ref"], data.get("client_request_id", ""))
            or str(data["agent_binding"]["workspace"]["root"]) != str(data.get("workspace"))):
        _refuse("the v2 child route binding is invalid")
    return data


def _short_id(*parts) -> str:
    return "subagent-" + canonical_sha256(list(parts))[:32]
