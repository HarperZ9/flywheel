"""subagent_roles.py -- the subagent contract: roles, specs, quorum.

The vocabulary children may speak and the seals that travel with them.
Roles are a fixed allowlist, each carrying the ONLY permissions it can
hold; escalation is refused at registration. A spec is sealed with a
canonical hash, and the child side re-validates every field before it
acts, because a child trusts nothing about its parent's file system.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256

SPEC_SCHEMA = "flywheel.subagent-spec/v1"
RESULT_SCHEMA = "flywheel.subagent-result/v1"
RUN_SCHEMA = "flywheel.subagent-run/v1"
SWARM_SCHEMA = "flywheel.subagent-swarm/v1"

QUORUM_POLICIES = ("all", "majority", "any")
MAX_CHILDREN = 8
MIN_TIMEOUT_S = 5.0
MAX_TIMEOUT_S = 3600.0
MAX_GOAL_CHARS = 4000
MAX_PROMPT_CHARS = 2000

#: The fixed role vocabulary. Each role carries the ONLY permissions it
#: may hold; anything more is refused at registration (least privilege).
ROLE_GRANTS = {
    "explore": frozenset(),
    "plan": frozenset(),
    "implement": frozenset(("allow_write",)),
    "verify": frozenset(("allow_exec",)),
    "review": frozenset(),
}

BUILTIN_PROMPTS = {
    "explore": "Survey the target read-only. Report structure, entry "
               "points, and risks.",
    "plan": "Decompose the goal into ordered steps, each with a check "
            "that decides it.",
    "implement": "Make the change in your own workspace. Keep edits "
                 "minimal.",
    "verify": "Run the checks that decide the goal. Report pass or fail "
              "with output.",
    "review": "Critique the proposed approach. Name concrete failure "
              "modes.",
}


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def validate_child(role: str, prompt: str = "", *,
                   allow_write: bool = False,
                   allow_exec: bool = False) -> dict:
    grants = ROLE_GRANTS.get(role)
    if grants is None:
        _refuse(f"unknown role: {role!r}")
    if not isinstance(prompt, str) or len(prompt) > MAX_PROMPT_CHARS:
        _refuse("the role prompt is missing or over the limit")
    if allow_write and "allow_write" not in grants:
        _refuse(f"role {role!r} cannot hold write authority")
    if allow_exec and "allow_exec" not in grants:
        _refuse(f"role {role!r} cannot hold exec authority")
    return {"role": role, "prompt": prompt,
            "allow_write": bool(allow_write),
            "allow_exec": bool(allow_exec)}


def with_role_prompt(child: dict) -> dict:
    """An un-prompted role carries its builtin procedure, so the spec
    the child receives is never promptless."""
    if not child["prompt"]:
        child["prompt"] = BUILTIN_PROMPTS[child["role"]]
    return child


def build_spec(*, swarm_id: str, child_id: str, goal: str, endpoint: str,
               model: str, max_steps: int, child: dict,
               workspace: Path, created_at: str) -> dict:
    spec = {
        "schema": SPEC_SCHEMA, "swarm_id": swarm_id, "child_id": child_id,
        "role": child["role"], "prompt": child["prompt"], "goal": goal,
        "endpoint": endpoint, "model": model, "max_steps": int(max_steps),
        "allow_write": child["allow_write"],
        "allow_exec": child["allow_exec"],
        "workspace": str(workspace), "created_at": created_at,
    }
    spec["spec_sha256"] = canonical_sha256(spec)
    return spec


def validate_spec(data: dict) -> dict:
    """The child side trusts nothing: re-check every field it acts on."""
    if not isinstance(data, dict) or data.get("schema") != SPEC_SCHEMA:
        _refuse("the file is not a subagent spec")
    validate_child(str(data.get("role")), str(data.get("prompt") or ""),
                   allow_write=bool(data.get("allow_write")),
                   allow_exec=bool(data.get("allow_exec")))
    digest = data.get("spec_sha256", "")
    body = {k: v for k, v in data.items() if k != "spec_sha256"}
    if not isinstance(digest, str) or canonical_sha256(body) != digest:
        _refuse("the spec seal does not match its content")
    goal = data.get("goal")
    if not isinstance(goal, str) or not goal or len(goal) > MAX_GOAL_CHARS:
        _refuse("the spec carries no usable goal")
    ws = data.get("workspace")
    if not isinstance(ws, str) or not ws:
        _refuse("the spec names no workspace")
    steps = data.get("max_steps")
    if isinstance(steps, bool) or not isinstance(steps, int) \
            or not 1 <= steps <= 12:
        _refuse("the spec max_steps is out of range")
    return data


def compose_goal(prompt: str, goal: str) -> str:
    return f"{prompt}\n\nGOAL: {goal}" if prompt else goal


def quorum(policy: str, completed: int, total: int) -> dict:
    """The fan-in rule is deterministic arithmetic, never judgment."""
    if policy not in QUORUM_POLICIES:
        _refuse(f"unknown quorum policy: {policy!r}")
    required = {"all": total, "any": 1,
                "majority": total // 2 + 1}[policy]
    return {"required": required, "completed": completed, "total": total,
            "verdict": "satisfied" if completed >= required
            else "unsatisfied"}


def child_status(exit_code: int, result_ok: bool) -> str:
    return "completed" if exit_code == 0 and result_ok else "failed"


def read_child_result(workspace: Path) -> "dict | None":
    path = Path(workspace) / "result.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != RESULT_SCHEMA:
        return None
    return data
