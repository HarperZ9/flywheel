"""Shared sealed swarm fan-in receipt construction."""
from __future__ import annotations

import hashlib
import json

from .accountable_hooks import (event_blocked, load_registry, run_hooks,
    subprocess_runner)
from .subagent_roles import SWARM_SCHEMA, quorum
from .subagent_store import save_swarm_receipt


def finalize_swarm(runner, rec: dict) -> None:
    receipts = [c["receipt"] for c in rec["children"]]
    completed = sum(1 for r in receipts if r["status"] == "completed")
    accepted = sum(1 for r in receipts if r.get("accepted"))
    counts = quorum(rec["quorum_policy"], completed, len(receipts))
    verified = quorum(rec["quorum_policy"], accepted, len(receipts))
    cert_children = [{"child_id": r["child_id"],
                      "chain_head": r.get("verdict_chain_head", ""),
                      "accepted": bool(r.get("accepted"))} for r in receipts]
    swarm_cert = {"children": cert_children, "accepted": accepted,
                  "cert_sha256": hashlib.sha256(
                      json.dumps(cert_children, sort_keys=True).encode()).hexdigest()[:16]}
    registry = load_registry(runner.root / "hooks" / "registry.json")
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
        "verified": {"accepted": accepted, "required": verified["required"],
                     "verdict": verified["verdict"]},
        "swarm_cert": swarm_cert,
        "children": receipts, "hook_receipts": hook_receipts,
        "event_blocked": event_blocked(hook_receipts),
        "created_at": rec["created_at"],
        "finished_at": runner._clock(),
        "does_not_prove": [
            "a satisfied completed quorum attests the children ran and reported; "
            "it does not prove the goal was achieved",
            "a satisfied verified quorum attests each counted child's chain was "
            "intact, its trajectory did not tamper with its grader, and any check "
            "it ran passed; it does not prove the child pursued the intended goal",
        ]}
    if rec.get("routing_schema"):
        receipt["routing_schema"] = rec["routing_schema"]
    save_swarm_receipt(receipt, run_root=runner.root)
    with runner._lock:
        rec["receipt"] = receipt
        rec["status"] = "sealed"
