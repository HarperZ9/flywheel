"""subagents.py -- role-prompted agent swarms with per-child receipts.

One goal fans out to N child agent loops. Each child runs in its own
process tree (argv, never a shell) inside its own scratch workspace,
under a fixed role whose authority is enforced at registration. Every
child is sealed a run receipt; a deterministic quorum rule fans the
children back in -- no learned model decides whether the swarm
satisfied its goal, only counted completions against the policy.
Fan-in fires the accountable hooks `agent.completed` event from the
run root's registry.

The contract lives in subagent_roles (roles, spec seals, quorum) and
subagent_store (persistence, production launcher); this module owns
the lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from .accountable_hooks import (
    event_blocked,
    load_registry,
    run_hooks,
    subprocess_runner,
)
from .evidence_json import canonical_sha256  # re-exported for seals
from .subagent_roles import (
    BUILTIN_PROMPTS,
    MAX_CHILDREN,
    MAX_GOAL_CHARS,
    MAX_PROMPT_CHARS,
    MAX_TIMEOUT_S,
    MIN_TIMEOUT_S,
    QUORUM_POLICIES,
    RESULT_SCHEMA,
    ROLE_GRANTS,
    RUN_SCHEMA,
    SPEC_SCHEMA,
    SWARM_SCHEMA,
    build_spec,
    child_status,
    compose_goal,
    quorum,
    read_child_result,
    validate_child,
    validate_spec,
    with_role_prompt,
)
from .subagent_store import (
    child_env,
    load_swarm_receipt,
    popen_handle,
    save_swarm_receipt,
    sealed_summaries,
    swarm_dir,
    worker_command,
)


def _refuse(msg: str) -> None:
    raise ValueError(msg)


class SwarmRunner:
    """Owns every swarm started in this process; seals receipts on fan-in."""

    def __init__(self, *, run_root, clock=None) -> None:
        self.root = Path(run_root)
        self._clock = clock or (lambda: time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._lock = threading.Lock()
        self._live: dict[str, dict] = {}

    def spawn(self, *, goal: str, endpoint: str, children: list[dict],
              quorum_policy: str = "majority", timeout_s: float = 600.0,
              max_steps: int = 6, model: str = "",
              handle_factory=None) -> dict:
        if not isinstance(goal, str) or not goal.strip() \
                or len(goal) > MAX_GOAL_CHARS:
            _refuse("the swarm goal is empty or over the limit")
        if not isinstance(endpoint, str) or not endpoint.strip() \
                or len(endpoint) > 200:
            _refuse("the swarm names no endpoint")
        if not isinstance(model, str) or len(model) > 200:
            _refuse("the model ref is invalid")
        if quorum_policy not in QUORUM_POLICIES:
            _refuse(f"unknown quorum policy: {quorum_policy!r}")
        if isinstance(timeout_s, bool) \
                or not isinstance(timeout_s, (int, float)) \
                or not MIN_TIMEOUT_S <= float(timeout_s) <= MAX_TIMEOUT_S:
            _refuse("timeout_s is outside the bounded window")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) \
                or not 1 <= max_steps <= 12:
            _refuse("max_steps is out of range")
        if not isinstance(children, list) \
                or not 1 <= len(children) <= MAX_CHILDREN:
            _refuse(f"a swarm carries 1..{MAX_CHILDREN} children")
        sealed_children = []
        for c in children:
            if isinstance(c, str):
                c = {"role": c}
            if not isinstance(c, dict):
                _refuse("every child binding is a role object")
            sealed_children.append(with_role_prompt(validate_child(
                str(c.get("role", "")), str(c.get("prompt") or ""),
                allow_write=bool(c.get("allow_write")),
                allow_exec=bool(c.get("allow_exec")))))
        swarm_id = "swarm_" + secrets.token_hex(6)
        sdir = swarm_dir(self.root, swarm_id)
        sdir.mkdir(parents=True, exist_ok=True)
        created_at = self._clock()
        records = []
        for child in sealed_children:
            child_id = "sa_" + secrets.token_hex(4)
            workspace = sdir / ("work_" + child_id)
            workspace.mkdir(parents=True, exist_ok=True)
            spec = build_spec(swarm_id=swarm_id, child_id=child_id,
                              goal=goal, endpoint=endpoint, model=model,
                              max_steps=max_steps, child=child,
                              workspace=workspace, created_at=created_at)
            spec_path = sdir / (child_id + ".spec.json")
            spec_path.write_text(
                json.dumps(spec, indent=2, sort_keys=True),
                encoding="utf-8")
            records.append({"child_id": child_id, "role": child["role"],
                            "spec": spec, "spec_path": spec_path,
                            "workspace": workspace})
        rec = {"swarm_id": swarm_id, "status": "running",
               "quorum_policy": quorum_policy, "timeout_s": timeout_s,
               "goal": goal, "endpoint": endpoint, "created_at": created_at,
               "handle_factory": handle_factory or popen_handle,
               "children": records}
        with self._lock:
            self._live[swarm_id] = rec
        threading.Thread(target=self._orchestrate, args=(rec,),
                         daemon=True, name=swarm_id).start()
        return {"schema": "flywheel.subagent-spawn-ack/v1",
                "swarm_id": swarm_id, "status": "running",
                "quorum_policy": quorum_policy, "timeout_s": timeout_s,
                "children": [{"child_id": c["child_id"], "role": c["role"]}
                             for c in records]}

    def _orchestrate(self, rec: dict) -> None:
        factory = rec["handle_factory"]
        for c in rec["children"]:
            started = time.monotonic()
            timed_out = False
            try:
                handle = factory(c["spec_path"], c["workspace"])
                exit_code, output = handle.wait(rec["timeout_s"])
            except TimeoutError:
                timed_out = True
                try:
                    handle.stop()
                except Exception:
                    pass
                exit_code, output = -1, ""
            except Exception:
                exit_code, output = -1, ""
            duration_ms = int((time.monotonic() - started) * 1000)
            result = read_child_result(c["workspace"])
            result_ok = bool(result) \
                and result.get("spec_sha256") == c["spec"]["spec_sha256"] \
                and result.get("status") == "completed"
            c["receipt"] = {
                "schema": RUN_SCHEMA, "swarm_id": rec["swarm_id"],
                "child_id": c["child_id"], "role": c["role"],
                "endpoint": rec["endpoint"],
                "spec_sha256": c["spec"]["spec_sha256"],
                "exit_code": exit_code,
                "output_sha256": (hashlib.sha256(output.encode()).hexdigest()
                                  if output else ""),
                "duration_ms": duration_ms, "timed_out": timed_out,
                "result_ok": result_ok,
                "status": ("timeout" if timed_out
                           else child_status(exit_code, result_ok)),
            }
        self._finalize(rec)

    def _finalize(self, rec: dict) -> None:
        receipts = [c["receipt"] for c in rec["children"]]
        completed = sum(1 for r in receipts if r["status"] == "completed")
        counts = quorum(rec["quorum_policy"], completed, len(receipts))
        registry = load_registry(self.root / "hooks" / "registry.json")
        hook_receipts = run_hooks(
            "agent.completed", registry,
            runner=subprocess_runner(timeout_s=15.0),
            context={"swarm_id": rec["swarm_id"],
                     "completed": counts["completed"],
                     "total": counts["total"]})
        receipt = {
            "schema": SWARM_SCHEMA, "swarm_id": rec["swarm_id"],
            "goal_sha256": hashlib.sha256(rec["goal"].encode()).hexdigest(),
            "endpoint": rec["endpoint"],
            "quorum_policy": rec["quorum_policy"], **counts,
            "children": receipts, "hook_receipts": hook_receipts,
            "event_blocked": event_blocked(hook_receipts),
            "created_at": rec["created_at"],
            "finished_at": self._clock(),
            "does_not_prove": [
                "a satisfied quorum attests the children ran and reported; "
                "it does not prove the goal was achieved",
            ],
        }
        save_swarm_receipt(receipt, run_root=self.root)
        with self._lock:
            rec["receipt"] = receipt
            rec["status"] = "sealed"

    def snapshot(self, swarm_id: str) -> "dict | None":
        with self._lock:
            rec = self._live.get(swarm_id)
        if rec is None:
            return None
        if rec["status"] == "running":
            return {"swarm_id": swarm_id, "status": "running",
                    "children": [{"child_id": c["child_id"],
                                  "role": c["role"], "state": "running"}
                                 for c in rec["children"]]}
        return {"swarm_id": swarm_id, "status": "sealed",
                "receipt": rec["receipt"]}

    def live_summaries(self) -> list[dict]:
        with self._lock:
            return [{"swarm_id": sid, "status": rec["status"],
                     "children": len(rec["children"])}
                    for sid, rec in self._live.items()]
