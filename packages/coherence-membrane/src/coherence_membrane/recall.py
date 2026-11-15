"""Symbolic recall + on-read re-verification for accountable memory.

verify_fresh re-checks a memory: source-backed memories re-perceive their subject and
re-judge it via reconcile; sourceless memories are fresh unless a 'supersedes' edge
points past them; an unresolved criterion/perceiver fails closed to UNVERIFIABLE.
Stdlib only; no embeddings -- recall is by id/type/tag/structure/graph-traversal.
"""
from __future__ import annotations

from dataclasses import dataclass

from .reconcile import reconcile
from .memory import MemoryRecord, MemoryStore
from .phash import MATCH, DRIFT, UNVERIFIABLE

_VERDICT_MAP = {"verified": MATCH, "refuted": DRIFT, "unverifiable": UNVERIFIABLE}


def _typed_ancestors(store: MemoryStore, node_id: str, edge_type: str) -> set:
    """Ancestors reachable by following only edges of `edge_type`. A node's
    edge_type is its relation to its parents; recurse a node's parents only
    when that node's edge_type matches."""
    g = store.graph
    if node_id not in g.nodes:
        return set()
    out, seen, stack = set(), set(), [node_id]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = g.nodes.get(nid)
        if node is None or node.edge_type != edge_type:
            continue
        for p in node.parents:
            out.add(p)
            stack.append(p)
    return out


def _is_superseded(record_id: str, store: MemoryStore) -> bool:
    """True iff some node supersedes record_id (reverse-edge scan)."""
    for node in store.graph.nodes.values():
        if node.edge_type == "supersedes" and record_id in node.parents:
            return True
    return False


def verify_fresh(record: MemoryRecord, store: MemoryStore, *,
                 criteria=None, perceivers=None) -> tuple[str, str]:
    """Return (verdict, reason). Priority: source-backed reconcile -> supersession -> UNVERIFIABLE."""
    # 1. source-backed: re-perceive + re-judge
    if record.criterion_ref is not None and record.perceive_ref is not None \
            and criteria is not None and perceivers is not None:
        crit = criteria.get(record.criterion_ref.name, record.criterion_ref.version)
        perceive = perceivers.get(record.perceive_ref.name)
        if crit is not None and perceive is not None:
            obs = reconcile(dict(record.perceive_ref.args), perceive=perceive, criterion=crit)
            verdict = _VERDICT_MAP.get(obs.data.get("verdict"), UNVERIFIABLE)
            return verdict, f"re-reconciled via {record.criterion_ref.name}@{record.criterion_ref.version}"
    # 2. graph-backed supersession
    if _is_superseded(record.id, store):
        return DRIFT, "superseded by a newer memory"
    # 3. fail-closed when a source was declared but could not be resolved
    if record.criterion_ref is not None or record.perceive_ref is not None:
        return UNVERIFIABLE, "criterion/perceiver unregistered -- cannot re-check"
    return MATCH, "no source and not superseded"


@dataclass(frozen=True)
class RecalledMemory:
    record: MemoryRecord
    freshness: str = ""   # MATCH/DRIFT/UNVERIFIABLE when re-verified, else ""
    reason: str = ""


def recall(store: MemoryStore, *, type=None, tags=None, match=None, traverse_from=None,
           verdict=None, reverify=False, criteria=None, perceivers=None, limit=None):
    """Symbolic recall. Facets AND together; verdict= forces re-verification + filters."""
    must_verify = reverify or verdict is not None
    if must_verify and (criteria is None or perceivers is None):
        raise ValueError("reverify/verdict filter requires criteria and perceivers")
    ids = set(store.records)
    if traverse_from is not None:
        node_id, edge = traverse_from
        ids &= _typed_ancestors(store, node_id, edge)
    candidates = [store.records[i] for i in ids]
    if type is not None:
        candidates = [r for r in candidates if r.type == type]
    if tags:
        want = set(tags)
        candidates = [r for r in candidates if want <= set(r.tags)]
    if match is not None:
        candidates = [r for r in candidates if match in r.claim]
    candidates.sort(key=lambda r: r.id)  # deterministic order

    out: list[RecalledMemory] = []
    for r in candidates:
        if must_verify:
            v, reason = verify_fresh(r, store, criteria=criteria, perceivers=perceivers)
            if verdict is not None and v != verdict:
                continue
            out.append(RecalledMemory(r, v, reason))
        else:
            out.append(RecalledMemory(r))
    return out[:limit] if limit is not None else out
