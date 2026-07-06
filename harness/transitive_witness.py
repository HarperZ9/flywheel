"""transitive_witness.py — compositional criterion-conservation over a
dependency DAG. The closure property the current literature does NOT publish.

Today every receipt is an island: `witness_envelope` re-checks ONE envelope;
`validate_chain` checks ONE run's internal links. Criterion-conservation does
not compose end-to-end. This module makes it compose: given a DAG of witnessed
results where each node cites the ancestors its verdict is GROUNDED on, a node
is MATCH only along a fully-MATCH dependency path. A single upstream DRIFT turns
every DOWNSTREAM-DEPENDENT node UNVERIFIABLE — while nodes that do not depend on
the drifted one keep their own verdict (localized degradation, not total
collapse). That path-conserved-MATCH is the novel object.

Positioning (honest, from the 2026-07-06 arXiv sweep): the *substrate* — a
citation/provenance DAG for agent results — is accepted prior art (PROV-AGENT,
2508.02866). The *re-witnessing closure* on top of it is not. Adopted from the
same sweep:
  - process-level (per-node) re-check, not outcome-only  (Trust-but-Verify survey 2508.16665)
  - paraconsistent glut/gap degradation so one drift doesn't collapse the DAG
    (Sound-and-Complete Neurosymbolic, 2507.09751): GLUT=DRIFT (a contradiction:
    re-check refutes the stored claim), GAP=UNVERIFIABLE (grounding cannot be
    confirmed). A descendant grounded on a glut becomes a GAP, not a glut.
  - adversarial no-receipt gate: a node without a receipt can never MATCH
    (AutoMegaKernel's zero-false-accept corpus, 2606.09682).

Not a breakthrough claim until it survives an adversarial false-accept corpus.
This is the kernel; the corpus is the next gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MATCH = "MATCH"
DRIFT = "DRIFT"            # glut: the node's own re-check refutes its stored verdict
UNVERIFIABLE = "UNVERIFIABLE"  # gap: grounding cannot be confirmed


@dataclass
class DepNode:
    """One witnessed result and the ancestors its verdict is GROUNDED on.
    `local` is the node's OWN re-witness verdict (process-level, per-node)."""
    id: str
    local: str                      # MATCH | DRIFT | UNVERIFIABLE
    deps: list[str] = field(default_factory=list)
    has_receipt: bool = True        # adversarial gate: no receipt -> never MATCH


def transitive_verdicts(nodes: list[DepNode]) -> dict[str, str]:
    """Fold local re-witness verdicts over the dependency DAG into transitive
    verdicts. Cycles and dangling deps collapse to UNVERIFIABLE (grounding cannot
    be established). Paraconsistent: a node's verdict depends only on its own
    re-check and its ancestors', so unrelated drift never touches it."""
    by_id = {n.id: n for n in nodes}
    memo: dict[str, str] = {}
    visiting: set[str] = set()

    def resolve(nid: str) -> str:
        if nid in memo:
            return memo[nid]
        node = by_id.get(nid)
        if node is None:
            return UNVERIFIABLE          # cited ancestor not present -> unconfirmable
        if nid in visiting:
            memo[nid] = UNVERIFIABLE      # cycle -> grounding cannot be established
            return UNVERIFIABLE
        visiting.add(nid)
        if not node.has_receipt:
            v = UNVERIFIABLE             # adversarial: no receipt, no MATCH
        elif node.local == DRIFT:
            v = DRIFT                    # localized glut (own claim refuted)
        elif node.local == UNVERIFIABLE:
            v = UNVERIFIABLE
        else:                            # local MATCH -> the grounding decides
            dep_vs = [resolve(d) for d in node.deps]
            if all(dv == MATCH for dv in dep_vs):
                v = MATCH                # criterion CONSERVED along a full path
            else:
                v = UNVERIFIABLE         # grounded on a glut/gap -> gap (not glut)
        visiting.discard(nid)
        memo[nid] = v
        return v

    return {n.id: resolve(n.id) for n in nodes}


def frontier_verdict(nodes: list[DepNode]) -> str:
    """The whole-DAG verdict: DRIFT if any node drifted; else UNVERIFIABLE if any
    node is unconfirmable; else MATCH. The single re-checkable object a caller
    trusts (or refuses) as one unit."""
    vs = transitive_verdicts(nodes).values()
    if any(v == DRIFT for v in vs):
        return DRIFT
    if any(v == UNVERIFIABLE for v in vs):
        return UNVERIFIABLE
    return MATCH


def dependents_of(nodes: list[DepNode], drifted_id: str) -> set[str]:
    """The set of nodes whose grounding (transitively) includes `drifted_id` —
    exactly the nodes that degrade when it drifts. The rest are provably
    unaffected (the localization guarantee, made explicit)."""
    by_id = {n.id: n for n in nodes}
    affected: set[str] = set()

    def touches(nid: str, seen: set[str]) -> bool:
        if nid == drifted_id:
            return True
        if nid in seen:
            return False
        seen.add(nid)
        node = by_id.get(nid)
        return bool(node) and any(touches(d, seen) for d in node.deps)

    for n in nodes:
        if n.id != drifted_id and touches(n.id, set()):
            affected.add(n.id)
    return affected


def from_envelopes(envelopes, local_verdicts: dict[str, str],
                   cite_field: str = "retrieved") -> list[DepNode]:
    """Build the DAG from real ProofEnvelopes. `local_verdicts` maps envelope id
    -> its re-witness verdict (caller supplies these from witness.witness_envelope,
    keeping re-verification in the witness organ, not here). Citation edges come
    from each envelope's `retrieved` receipts referencing ancestor ids."""
    nodes = []
    for env in envelopes:
        eid = getattr(env, "task_id", None) or getattr(env, "id", "")
        deps = []
        for r in (getattr(env, cite_field, None) or []):
            ref = r.get("source") if isinstance(r, dict) else None
            if ref:
                deps.append(str(ref))
        nodes.append(DepNode(
            id=str(eid), local=local_verdicts.get(str(eid), UNVERIFIABLE),
            deps=deps, has_receipt=bool(getattr(env, "oracle_output_hash", ""))))
    return nodes
