"""Validation and non-consuming preflight for v2 subagent routes."""
from __future__ import annotations

from pathlib import Path

from .gateway_operation import canonicalize_operation
from .gateway_provider_adapter import credential_slots, freeze_execution_plan
from .subagent_gateway_contract import _ROUTE_FIELDS
from .subagent_roles import compose_goal, validate_child, with_role_prompt


def _refuse(message: str) -> None:
    raise ValueError(message)


def is_v2_child(value: object) -> bool:
    return isinstance(value, dict) and "route" in value


def sealed_route(child: dict, parent: dict) -> tuple[dict, dict]:
    if not isinstance(child, dict):
        _refuse("every v2 child must be an object")
    sealed = with_role_prompt(validate_child(str(child.get("role", "")),
        str(child.get("prompt") or ""), allow_write=bool(child.get("allow_write")),
        allow_exec=bool(child.get("allow_exec"))))
    return sealed, validate_route(child.get("route"), parent, sealed)


def validate_route(route: object, parent: dict, child: dict) -> dict:
    required = {"endpoint", "model", "max_steps", "max_tokens", "timeout_s"}
    if not isinstance(route, dict) or set(route) - _ROUTE_FIELDS or required - set(route):
        _refuse("each v2 child route must name endpoint, model and budgets")
    bounded_int(route["max_steps"], 1, min(12, parent["budget"]["max_steps"]), "child max_steps")
    cap = parent["budget"]["max_tokens"]
    bounded_int(route["max_tokens"], 1, min(32768, cap or 32768), "child max_tokens")
    bounded_time(route["timeout_s"], 1, min(1800, float(parent["budget"]["timeout_s"])), "child timeout_s")
    child_caps_within_parent(child, parent)
    for field in ("endpoint", "model", "execution_mode", "tool_protocol"):
        if field in route and not isinstance(route[field], str):
            _refuse(f"child route {field} is invalid")
    refs = route.get("credential_refs", [])
    if not isinstance(refs, list) or any(type(ref) is not str for ref in refs):
        _refuse("child credential refs are invalid")
    return {**route, "credential_refs": list(refs)}


def operation_for_child(goal: str, child: dict, route: dict, workspace: Path) -> dict:
    op = {"goal": compose_goal(child["prompt"], goal), "endpoint": route["endpoint"],
        "root": str(workspace), "max_steps": route["max_steps"],
        "timeout_s": route["timeout_s"], "allow_write": child["allow_write"],
        "allow_exec": child["allow_exec"], "stream": False,
        "data_refs": [], "credential_refs": route["credential_refs"]}
    for field in ("model", "execution_mode", "tool_protocol", "max_tokens"):
        if route.get(field) not in (None, ""):
            op[field] = route[field]
    return op


def preflight_child_credentials(children: list[dict], parent: dict, *,
                                goal: str, state_root: Path,
                                workspace_root: Path | None) -> None:
    root = Path(workspace_root or state_root).resolve(strict=True)
    for child in children:
        sealed, route = sealed_route(child, parent)
        op = canonicalize_operation("agent.run", operation_for_child(
            goal, sealed, route, root))
        plan = freeze_execution_plan(op, owner_ref=parent["owner_ref"],
            state_root=state_root, workspace_root=root)
        credential_slots(op, parent["owner_ref"], state_root, plan=plan)


def child_caps_within_parent(child: dict, parent: dict) -> None:
    caps = parent["capabilities"]
    if child.get("allow_write") and not caps["allow_write"]:
        _refuse("child write authority exceeds parent authority")
    if child.get("allow_exec") and not caps["allow_exec"]:
        _refuse("child exec authority exceeds parent authority")


def bounded_int(value: object, low: int, high: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        _refuse(f"{name} is outside parent authority")


def bounded_time(value: object, low: float, high: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not low <= float(value) <= high:
        _refuse(f"{name} is outside parent authority")
