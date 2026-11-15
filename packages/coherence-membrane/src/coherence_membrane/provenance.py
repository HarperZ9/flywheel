"""Causal/temporal provenance -- a hash-chained DAG of what was perceived and done.

Perception and action leave a trail; this records it as a tamper-evident graph so
"what was perceived, in what order, authorising what action" is auditable. Nodes
are observations, actions, and gate decisions; edges are typed relationships
(observed-after, gated-by, caused-by). Each node's BINDING is a SHA-256 over its
content plus its parents' bindings -- the same keyless hash-chain the write-gate's
delegation chain uses -- so tampering with any node's content or its edges breaks
that node's binding and every binding downstream of it. verify() re-derives the
whole graph and reports VALID / BROKEN / UNVERIFIABLE.

What it proves, and what it does not:
  * The per-node chain proves no SURVIVING node was altered: you cannot silently
    rewrite a digest, change a kind/edge type, or re-parent/drop an edge on a node
    without verify() catching it (the change alters that node's binding, and every
    descendant's).
  * It does NOT, by itself, prove MEMBERSHIP: inserting a fabricated parentless
    node or deleting a childless one is internally self-consistent and the chain
    alone does not catch it. manifest() is the anchor that does -- a single digest
    over the whole node set the operator pins/signs out-of-band; pass it to
    verify(pinned_manifest=...) and any insertion or deletion is BROKEN.
  * It does NOT prove the CAUSALITY is real. A `caused-by` edge is an ASSERTED
    relationship (the operator/runtime states it); the chain proves the assertion
    was not altered, not that A truly caused B. Stated, not glossed.
  * Keyless binding is self-consistency, not non-repudiable identity: an adversary
    who rewrites a node AND recomputes every downstream binding (and the manifest,
    if unpinned) is not caught here. Real anti-forgery needs an external anchor (a
    signed/pinned manifest) -- the same honest boundary as the receipt and the
    delegation chain.

Inert and advisory: it records and re-derives; it never acts and grants no
authority. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .observation import Observation, sha256_hex

# Closed verdict lattice for graph integrity.
VALID = "VALID"
BROKEN = "BROKEN"
UNVERIFIABLE = "UNVERIFIABLE"
GRAPH_VERDICTS = frozenset({VALID, BROKEN, UNVERIFIABLE})

# Suggested edge vocabulary (not enforced -- any string is allowed, but these are
# the relationships the membrane's loop produces).
OBSERVED_AFTER = "observed-after"
GATED_BY = "gated-by"
CAUSED_BY = "caused-by"


def _strip_digest_prefix(digest: str) -> str:
    """Normalise a digest to bare hex (organs emit identity_sha256 as bare hex;
    provenance.digest carries a 'sha256:' prefix)."""
    return digest[len("sha256:"):] if digest.startswith("sha256:") else digest


def compute_binding(node_id: str, kind: str, digest: str, edge_type: str,
                    parent_bindings: list[str]) -> str:
    """SHA-256 over the node's content + its parents' bindings (canonical JSON).

    Parents are sorted so the binding is independent of the order parents were
    listed. Any change to id/kind/digest/edge_type or to any parent binding
    changes this binding -- and thus every descendant's binding.
    """
    payload = json.dumps(
        {"node_id": node_id, "kind": kind, "digest": digest, "edge_type": edge_type,
         "parents": sorted(parent_bindings)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return sha256_hex(payload)


@dataclass(frozen=True)
class ProvenanceNode:
    node_id: str
    kind: str            # "observation" | "action" | "gate-decision" | ...
    digest: str          # the witnessed/content digest this node stands for
    edge_type: str       # relationship to its parents
    parents: tuple[str, ...]
    binding: str

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "kind": self.kind, "digest": self.digest,
                "edge_type": self.edge_type, "parents": list(self.parents),
                "binding": self.binding}


@dataclass(frozen=True)
class GraphVerdict:
    verdict: str          # VALID / BROKEN / UNVERIFIABLE
    reasons: list[str] = field(default_factory=list)


class ProvenanceGraph:
    """An append-only, hash-chained DAG of perception/action provenance."""

    def __init__(self) -> None:
        self.nodes: dict[str, ProvenanceNode] = {}

    def add(self, node_id: str, kind: str, digest: str, *,
            parents: tuple | list = (), edge_type: str = OBSERVED_AFTER) -> ProvenanceNode:
        """Append a node. Parents must already exist (the graph is built in
        dependency order, which keeps it acyclic by construction)."""
        if node_id in self.nodes:
            raise ValueError(f"duplicate node_id {node_id!r}")
        parent_ids = tuple(parents)
        missing = [p for p in parent_ids if p not in self.nodes]
        if missing:
            raise ValueError(f"unknown parent(s) {missing}")
        binding = compute_binding(
            node_id, kind, digest, edge_type,
            [self.nodes[p].binding for p in parent_ids],
        )
        node = ProvenanceNode(node_id, kind, digest, edge_type, parent_ids, binding)
        self.nodes[node_id] = node
        return node

    def add_observation(self, node_id: str, observation: Observation, *,
                        parents: tuple | list = (), edge_type: str = OBSERVED_AFTER) -> ProvenanceNode:
        """Convenience: add a node standing for an Observation. The digest is the
        witnessed identity, normalised to bare hex (so it matches identity_sha256
        and the confirming_digests passed to has_confirming_look_ancestor)."""
        raw = observation.data.get("identity_sha256") or observation.provenance.digest
        return self.add(node_id, "observation", _strip_digest_prefix(raw),
                        parents=parents, edge_type=edge_type)

    def manifest(self) -> str:
        """A single pinnable digest over the WHOLE node set (sorted bindings +
        count). Pin or sign this out-of-band: it is the external anchor that closes
        the insert/delete-a-leaf gap (and the recompute-all-downstream forgery) the
        per-node chain alone cannot catch."""
        bindings = sorted(n.binding for n in self.nodes.values())
        payload = json.dumps({"count": len(bindings), "bindings": bindings},
                             sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return sha256_hex(payload)

    def verify(self, *, pinned_manifest: str | None = None) -> GraphVerdict:
        """Re-derive every node's binding and check integrity, order-independent.

        BROKEN if any stored binding does not match the re-derived one (tampered
        content or edge), a parent is unknown, or the graph has a cycle. With a
        `pinned_manifest`, also BROKEN if the node set changed since it was pinned
        (an insertion or deletion). Re-derivation is a topological fixpoint, so a
        valid graph serialised in any order verifies the same.
        """
        reasons: list[str] = []
        rederived: dict[str, str] = {}
        pending = dict(self.nodes)

        progressed = True
        while pending and progressed:
            progressed = False
            for node_id in list(pending):
                node = pending[node_id]
                if all(p in rederived for p in node.parents):
                    expected = compute_binding(
                        node.node_id, node.kind, node.digest, node.edge_type,
                        [rederived[p] for p in node.parents],
                    )
                    rederived[node_id] = expected
                    if expected != node.binding:
                        reasons.append(f"node {node_id!r} binding mismatch (tampered content or parent)")
                    del pending[node_id]
                    progressed = True

        for node_id, node in pending.items():  # unresolved: missing parent or cycle
            unknown = [p for p in node.parents if p not in self.nodes]
            if unknown:
                reasons.append(f"node {node_id!r} has unknown parent(s) {unknown}")
            else:
                reasons.append(f"node {node_id!r} is in a cycle (unresolvable parents)")

        if pinned_manifest is not None and self.manifest() != pinned_manifest:
            reasons.append("manifest mismatch: a node was inserted or deleted since it was pinned")

        if reasons:
            return GraphVerdict(BROKEN, reasons)
        if not self.nodes:
            return GraphVerdict(UNVERIFIABLE, ["empty graph -- nothing to verify"])
        return GraphVerdict(VALID, [])

    def ancestors(self, node_id: str) -> set[str]:
        """All transitive parents of a node (cycle-safe)."""
        if node_id not in self.nodes:
            raise KeyError(node_id)
        seen: set[str] = set()
        stack = list(self.nodes[node_id].parents)
        while stack:
            p = stack.pop()
            if p in seen or p not in self.nodes:
                continue
            seen.add(p)
            stack.extend(self.nodes[p].parents)
        return seen

    def has_confirming_look_ancestor(self, action_id: str, *,
                                     look_kind: str = "observation",
                                     confirming_digests: set[str] | None = None) -> bool:
        """Is an asserted confirming look an ANCESTOR of this action?

        Pure reachability over the attested edges -- NOT a temporal or causal proof:
        there are no timestamps, and the edge relationships are the operator's
        claims (the chain proves they were not altered, not that they are real).
        True iff `action_id` has an ancestor of kind `look_kind` (and, if
        `confirming_digests` is given, whose bare-hex digest is in that set).
        """
        if action_id not in self.nodes:
            raise KeyError(action_id)
        digests = ({_strip_digest_prefix(d) for d in confirming_digests}
                   if confirming_digests is not None else None)
        for aid in self.ancestors(action_id):
            node = self.nodes[aid]
            if node.kind == look_kind and (digests is None or node.digest in digests):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes.values()]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenanceGraph":
        """Reconstruct a graph from its serialised form WITHOUT recomputing
        bindings (the stored bindings are preserved verbatim so verify() can still
        detect tampering that happened before serialisation). Node order need not
        be topological -- verify() re-derives order-independently."""
        g = cls()
        for item in d.get("nodes", []):
            node = ProvenanceNode(
                node_id=str(item["node_id"]), kind=str(item["kind"]),
                digest=str(item["digest"]), edge_type=str(item["edge_type"]),
                parents=tuple(item.get("parents", [])), binding=str(item["binding"]),
            )
            g.nodes[node.node_id] = node
        return g
