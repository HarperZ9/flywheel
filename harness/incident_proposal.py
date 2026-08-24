"""incident_proposal.py -- the deterministic, read-only compilation.

The proposal compiles only the supplied admitted projection: source
facts must exist there, the case's head must still be the projection's
head, edges stay acyclic over known nodes, and the graph carries its
review requirements, limitations, and does_not_prove on its face. It
never accepts itself, never executes, never writes a lesson. Later
admission is a separately granted CAS command bound to the proposal and
graph hashes.
"""
from __future__ import annotations

from .evidence_json import canonical_sha256
from .incident_case import SCHEMA as CASE_SCHEMA

PROPOSAL_SCHEMA = "flywheel.incident-proposed-graph/v1"
_BANNED = ("accepted", "pass", "receipt", "execution", "command", "verdict")


def _compile_checks(case: dict, projection: dict) -> tuple[list, list]:
    """Deterministic check nodes over the failure's own summary: one
    review node per source fact, chained from the fact to the summary.
    Pure structure; nothing here runs."""
    summary = str(case["failure"]["summary"])
    checks = []
    edges = []
    fact_ids = sorted(ref["fact_id"] for ref in case["source_refs"])
    for i, fact_id in enumerate(fact_ids):
        node_id = f"chk_{abs(hash((fact_id, summary))) % 16**12:012x}"
        checks.append({"node_id": node_id, "kind": "review",
                       "of_fact": fact_id,
                       "statement": f"re-derive: {summary}"})
        edges.append([fact_id, node_id])
    return checks, edges


def _no_banned_fields(value: object, depth: int = 0) -> None:
    """Field-name scan: no key in the proposal may be acceptance or
    execution vocabulary. Prose that says what the proposal does NOT do
    is honest, not a violation."""
    if depth > 8:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(banned in lowered for banned in _BANNED):
                raise ValueError(
                    "the proposal must not carry the field vocabulary "
                    f"{key!r}")
            _no_banned_fields(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _no_banned_fields(child, depth + 1)


def compile_incident_proposal(
    *,
    case: dict,
    projection: dict,
    capability_sha256: str,
) -> dict:
    if case.get("schema") != CASE_SCHEMA:
        raise ValueError("the case is not an admitted incident case")
    if case.get("journey_ref") != projection.get("journey_ref"):
        raise ValueError("the projection names a different journey")
    if case.get("event_head_sha256") != projection.get("event_head_sha256"):
        raise ValueError("the journey head moved since the case was opened")
    known = {fact.get("fact_id") for fact in projection.get("facts", [])}
    source_ids = sorted(ref["fact_id"] for ref in case["source_refs"])
    if any(fact_id not in known for fact_id in source_ids):
        raise ValueError("a source fact is not in the admitted projection")
    checks, edges = _compile_checks(case, projection)
    proposal = {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": f"prp_{canonical_sha256({'case': case})[:32]}",
        "state": "proposed",
        "journey_ref": case["journey_ref"],
        "basis_event_head_sha256": case["event_head_sha256"],
        "capability_sha256": capability_sha256,
        "source_fact_ids": source_ids,
        "claims": [],
        "checks": checks,
        "edges": sorted(edges),
        "review_requirements": [
            "human review of every proposed check before any admission",
        ],
        "limitations": [
            "proposed structure only; no check ran and nothing was accepted",
        ],
        "does_not_prove": (
            "a proposed incident graph is not a diagnosis, not an "
            "acceptance, and not a receipt"),
    }
    _no_banned_fields(proposal)
    proposal["graph_sha256"] = canonical_sha256(
        {k: v for k, v in proposal.items() if k != "graph_sha256"})
    return proposal
