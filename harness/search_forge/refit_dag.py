# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N32 Gather Refit Provenance DAG (source_sha256 -> crop_bbox -> quote_hash -> claim_hash).

Builds and verifies deterministic acyclic provenance graphs linking raw source
artifacts through normalized spatial/byte crop regions and quote digests to
final claims. Uses Kahn topological sorting to reject cycles and dangling
orphan parents fail-closed, then seals a canonical SHA-256 DAG root digest.
Pure Python standard library only.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any

STAGE_ORDER: dict[str, int] = {
    "source_sha256": 0,
    "crop_bbox": 1,
    "quote_hash": 2,
    "claim_hash": 3,
}


@dataclass(frozen=True)
class DagNode:
    """Single node in an N32 provenance refit DAG."""

    node_id: str
    stage: str
    digest: str
    parents: tuple[str, ...] = ()
    crop_bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class DagVerdict:
    """Fail-closed verification outcome for an N32 refit provenance DAG."""

    ok: bool
    verdict: str
    topo_order: tuple[str, ...]
    dag_root_sha256: str
    errors: tuple[str, ...]


def validate_crop_bbox(bbox: tuple[float, float, float, float]) -> bool:
    """Validate normalized [x0, y0, x1, y1] bounding box inside [0.0, 1.0]."""
    if len(bbox) != 4:
        return False
    x0, y0, x1, y1 = bbox
    return 0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0


def _node_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_refit_chain(
    source_bytes: bytes,
    crop_bbox: tuple[float, float, float, float],
    quote_text: str,
    claim_text: str,
    prefix: str = "item0",
) -> tuple[DagNode, DagNode, DagNode, DagNode]:
    """Construct a valid 4-node source -> crop_bbox -> quote_hash -> claim_hash chain."""
    if not validate_crop_bbox(crop_bbox):
        raise ValueError(f"invalid normalized crop_bbox: {crop_bbox}")
    src_sha = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    n_src = DagNode(f"{prefix}:source", "source_sha256", src_sha, parents=())
    crop_sha = _node_digest({"parent": src_sha, "bbox": list(crop_bbox)})
    n_crop = DagNode(f"{prefix}:crop", "crop_bbox", crop_sha, parents=(n_src.node_id,), crop_bbox=crop_bbox)
    quote_sha = _node_digest({"parent": crop_sha, "quote": quote_text})
    n_quote = DagNode(f"{prefix}:quote", "quote_hash", quote_sha, parents=(n_crop.node_id,))
    claim_sha = _node_digest({"parent": quote_sha, "claim": claim_text})
    n_claim = DagNode(f"{prefix}:claim", "claim_hash", claim_sha, parents=(n_quote.node_id,))
    return n_src, n_crop, n_quote, n_claim


def _validate_nodes(nodes: list[DagNode] | tuple[DagNode, ...]) -> tuple[dict[str, DagNode], list[str]]:
    by_id: dict[str, DagNode] = {}
    errors: list[str] = []
    for node in nodes:
        if node.node_id in by_id:
            errors.append(f"duplicate_node_id:{node.node_id}")
        by_id[node.node_id] = node
        if node.stage not in STAGE_ORDER:
            errors.append(f"unknown_stage:{node.node_id}:{node.stage}")
        if not node.digest.startswith("sha256:") or len(node.digest) != 71:
            errors.append(f"invalid_digest:{node.node_id}")
        if node.stage == "crop_bbox":
            if node.crop_bbox is None or not validate_crop_bbox(node.crop_bbox):
                errors.append(f"invalid_crop_bbox:{node.node_id}")
        if node.stage != "source_sha256" and not node.parents:
            errors.append(f"orphan_non_root_node:{node.node_id}")
    return by_id, errors


def verify_refit_dag(nodes: list[DagNode] | tuple[DagNode, ...]) -> DagVerdict:
    """Verify DAG acyclicity (Kahn sort), parent existence, stage monotonicity, and root hash."""
    if not nodes:
        return DagVerdict(False, "REJECT", (), "", ("empty_dag",))
    by_id, errors = _validate_nodes(nodes)
    indeg: dict[str, int] = {n.node_id: 0 for n in nodes}
    children: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for node in nodes:
        for pid in node.parents:
            if pid not in by_id:
                errors.append(f"missing_parent:{node.node_id}->{pid}")
                continue
            p_stage = STAGE_ORDER.get(by_id[pid].stage, -1)
            c_stage = STAGE_ORDER.get(node.stage, -1)
            if p_stage >= c_stage:
                errors.append(f"stage_order_violation:{pid}->{node.node_id}")
            children[pid].append(node.node_id)
            indeg[node.node_id] += 1

    ready = deque(sorted(nid for nid, deg in indeg.items() if deg == 0))
    order: list[str] = []
    while ready:
        cur = ready.popleft()
        order.append(cur)
        for nxt in sorted(children[cur]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(by_id):
        errors.append("cycle_detected_by_kahn_sort")
    if errors:
        return DagVerdict(False, "REJECT", tuple(order), "", tuple(errors))

    canonical = [
        {"id": nid, "stage": by_id[nid].stage, "digest": by_id[nid].digest, "parents": list(by_id[nid].parents)}
        for nid in order
    ]
    root_sha = _node_digest({"schema": "n32-refit-dag/1", "nodes": canonical})
    return DagVerdict(True, "PASS", tuple(order), root_sha, ())
