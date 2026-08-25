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
import signal
import threading
import time

from .subagent_roles import RUN_SCHEMA, read_child_result
from .subagent_store import load_live_state, swarm_dir

_POLL_S = 0.5


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
    children = []
    for c in live["children"]:
        if not isinstance(c, dict) or not c.get("child_id") \
                or not c.get("workspace"):
            _refuse("the live state holds an invalid child row")
        children.append({"child_id": str(c["child_id"]),
                         "role": str(c.get("role") or ""),
                         "pid": c.get("pid"),
                         "spec": {"spec_sha256": str(c.get("spec_sha256")
                                                    or "")},
                         "workspace": c["workspace"], "handle": None})
    rec = {"swarm_id": swarm_id, "status": "running", "adopted": True,
           "quorum_policy": live.get("quorum_policy") or "majority",
           "goal": str(live.get("goal") or ""),
           "endpoint": str(live.get("endpoint") or ""),
           "created_at": str(live.get("created_at") or ""),
           "timeout_at": float(live.get("timeout_at") or 0.0),
           "cancel_requested": False, "children": children}
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
        if all(read_child_result(c["workspace"]) for c in rec["children"]):
            break
        time.sleep(_POLL_S)
    expired = time.time() >= deadline
    for c in rec["children"]:
        result = read_child_result(c["workspace"])
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
    runner._finalize(rec)


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
