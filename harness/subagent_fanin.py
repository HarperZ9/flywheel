"""Shared sealed swarm fan-in receipt construction."""
from __future__ import annotations

import hashlib
import json

from .accountable_hooks import (event_blocked, load_registry, run_hooks,
    subprocess_runner)
from .subagent_roles import SWARM_SCHEMA, quorum
from .subagent_store import save_swarm_receipt


def _cert_sha256(cert_children: list) -> str:
    return hashlib.sha256(json.dumps(cert_children, sort_keys=True).encode()).hexdigest()[:16]


def _cert_children(receipts: list) -> list:
    return [{"child_id": r["child_id"], "chain_head": r.get("verdict_chain_head", ""),
             "accepted": bool(r.get("accepted"))} for r in receipts]


def recheck_swarm_receipt(receipt: dict) -> dict:
    """Re-derive a sealed fan-in receipt from its own children, offline.

    MATCH when the counts, both quorum verdicts and the swarm certificate
    (each child's chain head and accepted flag, hashed) all re-derive from the
    children the receipt carries; DRIFT names every field that does not. It
    cannot re-run a child's own chain, which is not persisted."""
    if receipt.get("schema") != SWARM_SCHEMA:
        return {"verdict": "UNVERIFIABLE", "drift": ["schema"]}
    receipts = receipt.get("children") or []
    completed = sum(1 for r in receipts if r.get("status") == "completed")
    accepted = sum(1 for r in receipts if r.get("accepted"))
    counts = quorum(receipt["quorum_policy"], completed, len(receipts))
    verified = quorum(receipt["quorum_policy"], accepted, len(receipts))
    cert_children = _cert_children(receipts)
    cert = receipt.get("swarm_cert") or {}
    want = {"completed": (receipt.get("completed"), counts["completed"]),
            "total": (receipt.get("total"), counts["total"]),
            "required": (receipt.get("required"), counts["required"]),
            "verdict": (receipt.get("verdict"), counts["verdict"]),
            "verified.accepted": ((receipt.get("verified") or {}).get("accepted"), accepted),
            "verified.required": ((receipt.get("verified") or {}).get("required"),
                                  verified["required"]),
            "verified.verdict": ((receipt.get("verified") or {}).get("verdict"),
                                 verified["verdict"]),
            "swarm_cert.children": (cert.get("children"), cert_children),
            "swarm_cert.accepted": (cert.get("accepted"), accepted),
            "swarm_cert.cert_sha256": (cert.get("cert_sha256"), _cert_sha256(cert_children))}
    drift = [name for name, (have, derived) in want.items() if have != derived]
    return {"verdict": "DRIFT" if drift else "MATCH", "drift": drift,
            "children": len(receipts)}


def finalize_swarm(runner, rec: dict) -> None:
    receipts = [c["receipt"] for c in rec["children"]]
    completed = sum(1 for r in receipts if r["status"] == "completed")
    accepted = sum(1 for r in receipts if r.get("accepted"))
    counts = quorum(rec["quorum_policy"], completed, len(receipts))
    verified = quorum(rec["quorum_policy"], accepted, len(receipts))
    cert_children = _cert_children(receipts)
    swarm_cert = {"children": cert_children, "accepted": accepted,
                  "cert_sha256": _cert_sha256(cert_children)}
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
