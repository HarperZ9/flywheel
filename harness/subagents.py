"""Role-prompted agent swarms with per-child receipts and quorum fan-in."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

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
    LIVE_SCHEMA,
    child_env,
    detached_summaries,
    load_live_state,
    load_swarm_receipt,
    popen_handle,
    save_live_state,
    save_swarm_receipt,
    sealed_summaries,
    swarm_dir,
    worker_command,
)
from .subagent_rejoin import cancel_swarm, maybe_adopt


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

    def spawn(self, *, goal: str, endpoint: str = "", children: list[dict],
              quorum_policy: str = "majority", timeout_s: float = 600.0,
              max_steps: int = 6, model: str = "", parent_authority=None,
              workspace_root=None, state_root=None, operation_service=None,
              process_factory=None, handle_factory=None) -> dict:
        if not isinstance(goal, str) or not goal.strip() \
                or len(goal) > MAX_GOAL_CHARS:
            _refuse("the swarm goal is empty or over the limit")
        from .subagent_gateway_bridge import (aggregate_child_budget,
            attach_reservation, is_v2_child, parent_authority_summary,
            require_authorized_parent, reserve_gateway_swarm)
        bound_mode = isinstance(children, list) and any(is_v2_child(c) for c in children)
        if bound_mode:
            parent_authorized = require_authorized_parent(parent_authority)
            parent_authority = parent_authority_summary(parent_authorized)
            if operation_service is None or process_factory is None or state_root is None:
                _refuse("gateway operation service is required for v2 children")
        else:
            parent_authorized = None; parent_authority = None
        if not bound_mode:
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
        sealed_children = list(children) if bound_mode else []
        if bound_mode and any(not is_v2_child(c) for c in sealed_children):
            _refuse("every v2 child must carry its own route")
        aggregate = (aggregate_child_budget(
            sealed_children, parent_authority, float(timeout_s))
            if bound_mode else None)
        if not bound_mode:
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
        factory = handle_factory or popen_handle
        records = []
        for child in sealed_children:
            child_id = "sa_" + secrets.token_hex(4)
            workspace = sdir / ("work_" + child_id)
            workspace.mkdir(parents=True, exist_ok=True)
            if bound_mode:
                from .subagent_gateway_bridge import build_bound_spec
                spec = build_bound_spec(swarm_id=swarm_id, child_id=child_id,
                    goal=goal, child=child, workspace=workspace,
                    created_at=created_at, parent_authority=parent_authority,
                    workspace_root=workspace_root, state_root=state_root)
            else:
                spec = build_spec(swarm_id=swarm_id, child_id=child_id,
                                  goal=goal, endpoint=endpoint, model=model,
                                  max_steps=max_steps, child=child,
                                  workspace=workspace, created_at=created_at)
            records.append({"child_id": child_id, "role": child["role"],
                            "spec": spec, "spec_path": sdir / (child_id + ".spec.json"),
                            "workspace": workspace, "handle": None})
        if bound_mode:
            from .subagent_gateway_child import GatewayChildHandle
            reservation = reserve_gateway_swarm(
                operation_service, parent_authorized, swarm_id,
                [r["spec"] for r in records], aggregate, float(timeout_s))
            for r in records:
                r["spec"] = attach_reservation(r["spec"], reservation)
            def factory(spec_path, workspace):
                spec = next(r["spec"] for r in records if r["spec_path"] == spec_path)
                return GatewayChildHandle(spec, parent_authorized,
                    operation_service, process_factory, Path(state_root))
        for r in records:
            r["spec_path"].write_text(
                json.dumps(r["spec"], indent=2, sort_keys=True),
                encoding="utf-8")
            try:
                r["handle"] = factory(r["spec_path"], r["workspace"])
            except Exception:
                r["handle"] = None
        # The live state is what a restarted process adopts from: pids,
        # workspaces, and seals -- no in-memory handles required.
        from .subagent_gateway_contract import spec_live_fields
        endpoint_name = "mixed" if bound_mode else endpoint
        live = {
            "schema": LIVE_SCHEMA, "swarm_id": swarm_id,
            "created_at": created_at,
            "timeout_at": time.time() + float(timeout_s),
            "quorum_policy": quorum_policy, "goal": goal,
            "endpoint": endpoint_name,
            "children": [{"child_id": c["child_id"], "role": c["role"],
                          "pid": getattr(c["handle"], "pid", None),
                          "workspace": str(c["workspace"]),
                          "spec_sha256": c["spec"]["spec_sha256"],
                          **spec_live_fields(c["spec"])}
                         for c in records],
        }
        if bound_mode:
            live["routing_schema"] = "flywheel.subagent-routing/v2"
            live["state_root"] = str(Path(state_root))
        save_live_state(live, run_root=self.root)
        rec = {"swarm_id": swarm_id, "status": "running",
                "quorum_policy": quorum_policy, "timeout_s": timeout_s,
                "goal": goal, "endpoint": endpoint_name, "created_at": created_at,
                "cancel_requested": False, "children": records}
        if bound_mode:
            rec["routing_schema"] = "flywheel.subagent-routing/v2"
        with self._lock:
            self._live[swarm_id] = rec
        threading.Thread(target=self._orchestrate, args=(rec,),
                         daemon=True, name=swarm_id).start()
        return {"schema": "flywheel.subagent-spawn-ack/v1",
                "swarm_id": swarm_id, "status": "running",
                "quorum_policy": quorum_policy, "timeout_s": timeout_s,
                "children": [{"child_id": c["child_id"], "role": c["role"],
                              **spec_live_fields(c["spec"])}
                              for c in records]}

    def _orchestrate(self, rec: dict) -> None:
        for c in rec["children"]:
            started = time.monotonic()
            timed_out = False
            handle = c["handle"]
            try:
                if handle is None:
                    raise ValueError("the child never launched")
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
            if rec.get("cancel_requested") and not result_ok:
                status = "cancelled"
            elif timed_out:
                status = "timeout"
            else:
                status = child_status(exit_code, result_ok)
            verdict = result.get("verdict") if isinstance(result, dict) else None
            from .subagent_gateway_contract import spec_receipt_fields
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
                "status": status,
                # a child counts toward the VERIFIED quorum only if it both reported
                # and its own witnessed verdict re-derives to accepted; a mere exit 0
                # is not enough. chain_head binds this child into the swarm_cert.
                "accepted": bool(result_ok and isinstance(verdict, dict)
                                 and verdict.get("accepted")),
                "verdict_chain_head": (verdict or {}).get("chain_head", ""),
                **spec_receipt_fields(c["spec"], result),
            }
        self._finalize(rec)

    def _finalize(self, rec: dict) -> None:
        from .subagent_fanin import finalize_swarm
        finalize_swarm(self, rec)

    def snapshot(self, swarm_id: str) -> "dict | None":
        with self._lock:
            rec = self._live.get(swarm_id)
        if rec is None and maybe_adopt(self, swarm_id):
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

    def cancel(self, swarm_id: str, *, killer=None) -> dict:
        return cancel_swarm(self, swarm_id, killer=killer)

    def live_summaries(self) -> list[dict]:
        with self._lock:
            return [{"swarm_id": sid, "status": rec["status"],
                     "children": len(rec["children"])}
                    for sid, rec in self._live.items()]
