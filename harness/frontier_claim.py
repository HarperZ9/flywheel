"""frontier_claim.py -- the lossless frontier claim record.

A claim binds one journey to a source and a proposition. The eight
legacy observation fields ride along verbatim; the projection owns how
they group. Nothing here scores, ranks, or aggregates.
"""
from __future__ import annotations

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.frontier-claim/v1"

#: The eight legacy observation fields, carried verbatim. The projection
#: assigns each to its axis; this module only preserves them.
OBSERVATION_FIELDS = (
    "review_state", "verdict", "evidence_kind", "community_state",
    "novelty_state", "fidelity_state", "freshness_state",
    "reproduction_state",
)


def new_frontier_claim(
    *,
    claim_id: str,
    journey_ref: str,
    source: dict,
    proposition: dict,
    created_at: str,
    **observation,
) -> dict:
    if not claim_id.startswith("clm_"):
        raise ValueError("claim id is not a claim ref")
    if not journey_ref.startswith("jrn_"):
        raise ValueError("journey ref is not a journey ref")
    if not isinstance(source, dict) or not source:
        raise ValueError("a claim names its source")
    if not isinstance(proposition, dict) or not proposition.get("statement"):
        raise ValueError("a claim carries a proposition statement")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError("created_at is required")
    unknown = set(observation) - set(OBSERVATION_FIELDS)
    if unknown:
        raise ValueError(f"unknown observation fields: {sorted(unknown)}")
    claim = {
        "schema": SCHEMA,
        "claim_id": claim_id,
        "journey_ref": journey_ref,
        "identification": {
            "source": source,
            "proposition": proposition,
            "created_at": created_at,
        },
    }
    for field in OBSERVATION_FIELDS:
        if field in observation:
            claim[field] = observation[field]
    claim["claim_sha256"] = canonical_sha256(
        {k: v for k, v in claim.items() if k != "claim_sha256"})
    return claim
