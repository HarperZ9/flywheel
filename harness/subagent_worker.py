"""subagent_worker.py -- the child side of a subagent swarm.

Runs as `python -m harness.subagent_worker <spec.json>` inside the
child's own workspace. It validates the issued spec (sealed, role
within its grants), folds the role prompt into the goal, drives the
gated agent loop through router_agent, and seals a result.json that
the parent hashes into the child's run receipt. Exit codes:
0 completed, 2 the agent loop failed, 3 the spec was refused.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .router_agent import run_router_agent
from .subagents import RESULT_SCHEMA, compose_goal, validate_spec

EXIT_COMPLETED = 0
EXIT_FAILED = 2
EXIT_BAD_SPEC = 3


def write_result(workspace: Path, spec: dict, status: str, **extra) -> None:
    payload = {"schema": RESULT_SCHEMA,
               "spec_sha256": spec["spec_sha256"],
               "role": spec["role"], "status": status}
    payload.update(extra)
    (Path(workspace) / "result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def execute(spec: dict, *, agent=None) -> int:
    agent = agent or run_router_agent
    workspace = Path(spec["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        result = agent(compose_goal(str(spec.get("prompt") or ""),
                                    str(spec["goal"])),
                       str(spec["endpoint"]), root=str(workspace),
                       allow_write=bool(spec.get("allow_write")),
                       allow_exec=bool(spec.get("allow_exec")),
                       max_steps=int(spec["max_steps"]),
                       model=(str(spec.get("model")) or None))
    except Exception as exc:
        write_result(workspace, spec, "failed", error=type(exc).__name__)
        return EXIT_FAILED
    extra = {"final_excerpt": str(result.get("final") or "")[:2000]}
    if result.get("tests_pass_trusted") is not None:
        extra["tests_pass_trusted"] = bool(result["tests_pass_trusted"])
    write_result(workspace, spec, "completed", **extra)
    return EXIT_COMPLETED


def main(argv: list) -> int:
    if len(argv) != 1:
        return EXIT_BAD_SPEC
    try:
        spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        validate_spec(spec)
    except (OSError, ValueError):
        return EXIT_BAD_SPEC
    return execute(spec)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
