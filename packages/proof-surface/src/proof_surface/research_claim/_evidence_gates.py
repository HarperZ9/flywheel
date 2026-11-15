"""Bind the shared family evidence gates to the research-claim ladder.

Three optional disclosure fields, three honesty gates: declared_branches (a
fenced prover branch claims no verdict and is not citable support),
witness_tier (the promotion rung may not exceed the strongest executed
verifier tier), and evidence_classes (single-modality evidence caps at
HYPOTHESIS; the verified/fact tier starts at CRUCIBLE_MATCH and requires an
independent class). Off-ladder honesty rungs (UNVERIFIABLE, REFUTED) claim no
achievement and are never capped.
"""

from __future__ import annotations

from typing import Any

from .._branches import (
    promotion_summary_surfaces,
    reject_fenced_branch_citations,
    validate_declared_branches,
)
from .._evidence_classes import (
    enforce_evidence_independence,
    validate_evidence_classes,
)
from .._validate import Issue
from .._witness_tier import enforce_no_tier_inflation, validate_witness_tier

# The positive promotion ladder, weakest to strongest, aligned 1:1 with the
# shared VERIFIER_TIERS order. UNVERIFIABLE and REFUTED are off-ladder.
RUNG_RANK = {
    "SOURCE_LEAD": 0,
    "HYPOTHESIS": 1,
    "IDENTITY": 2,
    "PROBE_MATCH": 3,
    "CRUCIBLE_MATCH": 4,
    "LAW_CANDIDATE": 5,
}

# The verified/fact tier of the ladder (dogfood 0126 binding): CRUCIBLE_MATCH
# and above. Single-modality evidence is capped at HYPOTHESIS, below the fact
# tier, so reaching the fact tier requires a non-single-modality class.
FACT_TIER_RANK = RUNG_RANK["CRUCIBLE_MATCH"]
SINGLE_MODALITY_CAP_RANK = RUNG_RANK["HYPOTHESIS"]
assert SINGLE_MODALITY_CAP_RANK < FACT_TIER_RANK


def validate_evidence_gates(data: dict[str, Any], issues: list[Issue]) -> None:
    """Run the three optional family evidence gates against a packet."""
    promotion = data.get("promotion")
    branches = data.get("declared_branches")
    validate_declared_branches(branches, issues)
    reject_fenced_branch_citations(branches, promotion_summary_surfaces(data), issues)
    tier = data.get("witness_tier")
    validate_witness_tier(tier, issues)
    enforce_no_tier_inflation(tier, promotion, RUNG_RANK, issues)
    classes = data.get("evidence_classes")
    validate_evidence_classes(classes, issues)
    enforce_evidence_independence(
        classes, promotion, RUNG_RANK, SINGLE_MODALITY_CAP_RANK, issues
    )
