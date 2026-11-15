"""receipt.py -- a re-derivable receipt for a plexus plan or route.

A plan is a claim: "given THESE manifests, this is the wiring." The receipt binds the
derivation to the exact manifests it came from: the content hash of every organ in the
plan, plus a hash over the derived body. So a stranger holding the mesh and the plan
re-derives it and confirms the receipt, and a manifest that changed since the plan is
caught -- the wiring silently shifting under you is the failure this prevents.

verify_plan re-derives the plan FROM THE MESH (never trusting the plan's stored body),
so a forger who tampers the body and recomputes the hash is still caught. Zero-dep.
"""
from __future__ import annotations

import hashlib
import json

from .manifest import content_hash

SCHEMA = "plexus.plan-receipt/1"
METHOD_VERSION = "plexus-plan/1"


def _plan_organs(plan: dict) -> set:
    """Every organ the plan references, so each one's manifest is bound to the receipt."""
    organs: set = set()
    organs.update(plan.get("order") or [])
    for key in ("source", "target"):
        if plan.get(key):
            organs.add(plan[key])
    for key in ("hops", "path"):
        rows = plan.get(key)
        if isinstance(rows, list):        # route's `hops` is an int count, skip it; `path` is the list
            for hop in rows:
                if isinstance(hop, dict):
                    organs.update(x for x in (hop.get("producer"), hop.get("consumer")) if x)
    return organs


def _plan_body_sha(plan: dict) -> str:
    body = {k: v for k, v in plan.items() if k != "receipt"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_plan_receipt(mesh, plan: dict) -> dict:
    """Bind the plan to the content hash of every organ it references plus its body hash."""
    organs = sorted(o for o in _plan_organs(plan) if o in mesh.manifests)
    manifest_shas = {o: content_hash(mesh.manifests[o]) for o in organs}
    return {"schema": SCHEMA, "method_version": METHOD_VERSION,
            "manifest_shas": manifest_shas, "plan_sha256": _plan_body_sha(plan)}


def verify_plan(plan: dict, mesh) -> bool:
    """Re-derive the plan from the mesh and confirm its receipt. A tampered body or a
    manifest that changed since the plan both fail. Read-only."""
    r = plan.get("receipt")
    if not isinstance(r, dict) or r.get("method_version") != METHOD_VERSION:
        return False
    from .plan import plan_to, route
    if "source" in plan and "target" in plan:
        fresh = route(mesh, plan["source"], plan["target"])
    elif "target" in plan:
        fresh = plan_to(mesh, plan["target"])
    else:
        return False
    return build_plan_receipt(mesh, fresh) == r
