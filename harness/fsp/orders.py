"""Orders: throttle, halt a named workload, and lift (SPEC.md section 8).

Times are integer milliseconds. A throttle level is an integer percent of
rated throughput. Workload tags are opaque 32-byte values the operator
derives with a secret salt, so the log never names a job.
"""

from __future__ import annotations

import hashlib
import hmac

from .canon import fingerprint
from .crypto import envelope
from .merkle import MerkleTree

ACTIONS = ("throttle", "halt", "lift")


def workload_tag(salt: bytes, job_name: str) -> str:
    return hmac.new(salt, job_name.encode("utf-8"), hashlib.sha256).hexdigest()


def device_set_tree(device_keys: list[str]) -> MerkleTree:
    tree = MerkleTree()
    for key in sorted(device_keys):
        tree.append(key.encode("ascii"))
    return tree


def scope_proof(device_keys: list[str], device_key: str) -> dict:
    ordered = sorted(device_keys)
    tree = device_set_tree(ordered)
    index = ordered.index(device_key)
    return {"index": index, "size": len(ordered),
            "path": [h.hex() for h in tree.inclusion_proof(index, len(ordered))]}


def order_body(action: str, cluster_id: str, device_set_root: str, *,
               workload_tags: list[str] | None = None, level: int | None = None,
               criterion: dict, evidence: list[dict], convergence: dict,
               dependent_notice: dict | None, issued_ms: int, effective_ms: int,
               expires_ms: int, renews: str | None = None, lifts: str | None = None,
               rate: dict | None = None, appeal_route: str = "panel-1") -> dict:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action}")
    return {
        "action": action,
        "scope": {"cluster_id": cluster_id, "device_set_root": device_set_root,
                  "workload_tags": sorted(workload_tags or [])},
        "level": level,
        "criterion": criterion,
        "evidence": evidence,
        "evidence_fp": fingerprint("evidence", evidence),
        "sealed_summary_fp": fingerprint("sealed-summary", {"evidence": evidence}),
        "convergence": convergence,
        "dependent_notice": dependent_notice,
        "issued_ms": issued_ms, "effective_ms": effective_ms, "expires_ms": expires_ms,
        "renews": renews, "lifts": lifts,
        "rate": rate or {"scope_seq": 0, "window_count": 0},
        "appeal_route": appeal_route,
    }


def sign_order(body: dict, seats: list) -> dict:
    return envelope("order", body, [s.signer for s in seats])
