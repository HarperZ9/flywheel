"""subagent_rejoin.py -- cross-restart swarm control.

A gateway restart orphans its running swarms: the child processes keep
going, but nobody is waiting on them. This module reattaches. The
spawn-time live state (<swarm_dir>/live.json) carries each child's pid,
workspace, and spec seal; adoption rebuilds a runner record from that
file alone and watches the workspaces for result files instead of
process handles. Cancellation works the same way after a restart: it
kills the recorded pids and seals what actually finished, marking the
rest cancelled -- never silently successful.

Every adopted child receipt is stamped "reattached": true, because a
receipt assembled from disk evidence honestly differs from one that
held the process handle.
"""
from __future__ import annotations

import os
import json
import signal
import threading
import time
from pathlib import Path

from .subagent_roles import RUN_SCHEMA, read_child_result, validate_spec
from .subagent_store import load_live_state, swarm_dir

_POLL_S = 0.5
_ROUTING_SCHEMA_V2 = "flywheel.subagent-routing/v2"
_SPEC_SCHEMA_V2 = "flywheel.subagent-spec/v2"


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def pid_killer():
    """The production killer: TerminateProcess via os.kill, errors
    reported, never raised."""
    def kill(pid) -> bool:
        try:
            os.kill(int(pid), signal.SIGTERM)
            return True
        except (OSError, TypeError, ValueError):
            return False
    return kill


def maybe_adopt(runner, swarm_id: str) -> bool:
    """Adopt a detached swarm if it exists on disk and is not already
    owned by this process. Returns True when a record now exists."""
    with runner._lock:
        if swarm_id in runner._live:
            return True
    sdir = swarm_dir(runner.root, swarm_id)
    if (sdir / "swarm.json").is_file():
        return False
    live = load_live_state(sdir / "live.json")
    if live is None or live.get("swarm_id") != swarm_id:
        return False
    v2 = live.get("routing_schema") == _ROUTING_SCHEMA_V2
    children = []
    for c in live["children"]:
        if not isinstance(c, dict) or not c.get("child_id") \
                or not c.get("workspace"):
            _refuse("the live state holds an invalid child row")
        spec = _adopted_spec(sdir, c, v2)
        children.append({"child_id": str(c["child_id"]),
                         "role": str(c.get("role") or ""),
                         "pid": c.get("pid"),
                         "spec": spec,
                         "workspace": c["workspace"], "handle": None})
    rec = {"swarm_id": swarm_id, "status": "running", "adopted": True,
           "quorum_policy": live.get("quorum_policy") or "majority",
           "goal": str(live.get("goal") or ""),
           "endpoint": str(live.get("endpoint") or ""),
           "created_at": str(live.get("created_at") or ""),
           "timeout_at": float(live.get("timeout_at") or 0.0),
           "cancel_requested": False, "children": children}
    if v2:
        rec["routing_schema"] = _ROUTING_SCHEMA_V2
        rec["state_root"] = str(live.get("state_root") or "")
    with runner._lock:
        existing = runner._live.get(swarm_id)
        if existing is not None:
            return True
        runner._live[swarm_id] = rec
    threading.Thread(target=_watch_adopted, args=(runner, rec),
                     daemon=True, name="adopt-" + swarm_id).start()
    return True


def _watch_adopted(runner, rec: dict) -> None:
    deadline = rec["timeout_at"]
    while not rec["cancel_requested"] and time.time() < deadline:
        if all(_adopted_result(runner, rec, c) for c in rec["children"]):
            break
        time.sleep(_POLL_S)
    expired = time.time() >= deadline
    for c in rec["children"]:
        result = _adopted_result(runner, rec, c)
        result_ok = bool(result) \
            and result.get("spec_sha256") == c["spec"]["spec_sha256"] \
            and result.get("status") == "completed"
        if result_ok:
            status = "completed"
        elif rec["cancel_requested"]:
            status = "cancelled"
        else:
            status = "timeout" if expired else "failed"
        c["receipt"] = {
            "schema": RUN_SCHEMA, "swarm_id": rec["swarm_id"],
            "child_id": c["child_id"], "role": c["role"],
            "endpoint": rec["endpoint"],
            "spec_sha256": c["spec"]["spec_sha256"],
            "exit_code": None, "output_sha256": "",
            "duration_ms": 0, "timed_out": expired and not result_ok,
            "result_ok": result_ok, "reattached": True,
            "status": status,
        }
        verdict = result.get("verdict") if isinstance(result, dict) else None
        c["receipt"]["accepted"] = bool(result_ok and isinstance(verdict, dict)
                                       and verdict.get("accepted"))
        c["receipt"]["verdict_chain_head"] = (verdict or {}).get(
            "chain_head", "")
        if c["spec"].get("schema") == _SPEC_SCHEMA_V2:
            from .subagent_gateway_contract import spec_receipt_fields
            c["receipt"].update(spec_receipt_fields(c["spec"], result))
    runner._finalize(rec)


def _adopted_spec(sdir: Path, row: dict, v2: bool) -> dict:
    digest = str(row.get("spec_sha256") or "")
    if not v2:
        return {"spec_sha256": digest}
    try:
        path = Path(sdir) / (str(row["child_id"]) + ".spec.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        spec = validate_spec(data)
        if spec.get("spec_sha256") != digest:
            raise ValueError
        for key in ("operation_ref", "operation_sha256",
                    "agent_binding_sha256"):
            if row.get(key) and row.get(key) != spec.get(key):
                raise ValueError
        return spec
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"spec_sha256": digest}


def _adopted_result(runner, rec: dict, child: dict) -> "dict | None":
    result = read_child_result(child["workspace"])
    if result is not None:
        return result
    if child["spec"].get("schema") == _SPEC_SCHEMA_V2:
        return _materialize_gateway_result(runner, rec, child)
    return None


def _materialize_gateway_result(runner, rec: dict, child: dict) -> "dict | None":
    spec = child["spec"]
    state = str(rec.get("state_root") or "")
    if not state:
        return None
    try:
        from .gateway_operations import GatewayOperations
        from .subagent_gateway_child import operation_result_fields
        service = GatewayOperations(Path(state), clock=runner._clock)
        owner = spec["parent_authority"]["owner_ref"]
        snapshot = service.snapshot(owner, spec["operation_ref"])
        if snapshot.state not in service.terminal_states:
            return None
        projection = service.result(owner, spec["operation_ref"])["result"]
        status = "completed" if snapshot.state == "completed" else "failed"
        payload = {"schema": "flywheel.subagent-result/v1",
                   "spec_sha256": spec["spec_sha256"],
                   "role": spec.get("role", ""), "status": status,
                   **operation_result_fields(spec, snapshot.as_json(),
                                             projection, service.state_root)}
        workspace = Path(child["workspace"])
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "result.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    except Exception:
        return None


def cancel_swarm(runner, swarm_id: str, *, killer=None) -> dict:
    """Stop every child of a running swarm -- in-process handles or
    detached pids -- then let the finalizer seal the honest outcome."""
    killer = killer or pid_killer()
    with runner._lock:
        rec = runner._live.get(swarm_id)
    if rec is None:
        if maybe_adopt(runner, swarm_id):
            with runner._lock:
                rec = runner._live.get(swarm_id)
    if rec is None or rec["status"] != "running":
        state = "unknown" if rec is None else "sealed"
        return {"code": "CANCEL_UNAVAILABLE", "swarm_id": swarm_id,
                "state": state}
    rec["cancel_requested"] = True
    killed, refused = 0, 0
    for c in rec["children"]:
        handle = c.get("handle")
        if handle is not None:
            try:
                if handle.stop():
                    killed += 1
                else:
                    refused += 1
            except Exception:
                refused += 1
            continue
        if c.get("pid"):
            if killer(c["pid"]):
                killed += 1
            else:
                refused += 1
    with runner._lock:
        state = rec["status"]
    return {"swarm_id": swarm_id, "state": "cancelled",
            "killed": killed, "refused": refused}
