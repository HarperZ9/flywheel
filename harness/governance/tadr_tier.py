"""tadr_tier.py -- the TADR consequence-based tier system.

Cloned from proof_surface/_witness_tier.py's pattern: a closed ranked tier
set with a no-inflation gate. TADR tiers are consequence-based (T1=localized,
T2=severe/scalable, T3=catastrophic/irreversible), orthogonal to operational
severity and verifier strength.

Stage A (consequence overrides) classifies as T3 or T2 when any credible
scenario matches a catastrophic or severe override. Stage B (structured
assessment) uses 12 dimensions to refine within the override floor.

The TADR manual's section 3 defines the assignment rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Closed ranked tier order, weakest to strongest.
TADR_TIERS = {"T1": 1, "T2": 2, "T3": 3}

# Surface modifiers (section 4). Do not reduce the tier.
TADR_MODIFIERS = frozenset({
    "P",  # physical process or facility
    "B",  # biological or public-health system
    "R",  # radiological or nuclear system
    "D",  # digital, cyber, or software system
    "A",  # AI, model, agent, or autonomous system
    "I",  # information, media, or influence system
    "F",  # financial, market, or transaction system
    "H",  # human, insider, coercion, or organizational system
    "S",  # supply-chain or vendor system
    "E",  # environmental or ecological system
    "G",  # governance, legal, or institutional system
    "X",  # cross-domain blended threat
})

# Stage A: T3 consequence overrides (section 3, Stage A).
T3_OVERRIDES = frozenset({
    "mass-casualty-potential",
    "irreversible-environmental-harm",
    "collapse-of-essential-systems",
    "uncontrolled-propagation-across-jurisdictions",
    "autonomous-action-defeats-human-intervention",
    "strategic-destabilization",
    "new-pathway-to-catastrophic-harm",
    "corruption-of-evidence-oversight-controls",
    "inability-to-verify-deployment-bounds",
    "high-uncertainty-with-catastrophic-upper-bound",
})

# Stage A: T2 consequence overrides.
T2_OVERRIDES = frozenset({
    "severe-injury-affecting-multiple-persons",
    "multi-site-disruption",
    "compromise-of-regulated-data",
    "repeated-scalable-abuse",
    "election-market-health-interference",
    "compromise-of-critical-supplier",
    "cross-domain-escalation-potential",
    "recovery-measured-in-weeks-or-months",
})

# Structured assessment dimensions (section 3, Stage B).
ASSESSMENT_DIMENSIONS = (
    "consequence_magnitude",
    "population_or_system_scope",
    "propagation_speed",
    "reversibility",
    "autonomy",
    "accessibility_to_threat_actors",
    "stealth_and_attribution_difficulty",
    "cross_system_coupling",
    "control_maturity",
    "evidence_quality",
    "uncertainty",
    "recovery_complexity",
)


def tier_rank(tier: str) -> int:
    """Return the numeric rank of a tier (1=T1, 2=T2, 3=T3)."""
    return TADR_TIERS.get(tier, 0)


def validate_tier(tier: str) -> bool:
    """True if tier is a valid TADR tier."""
    return tier in TADR_TIERS


def validate_modifiers(modifiers: list[str]) -> list[str]:
    """Return invalid modifiers (empty list = all valid)."""
    return [m for m in modifiers if m not in TADR_MODIFIERS]


def enforce_no_tier_inflation(authorized_tier: str,
                              requested_tier: str) -> bool:
    """Reject operation above authorized tier.

    A system classified T1 cannot perform T3 actions. The highest credible
    consequence carries more weight than the most likely minor consequence.
    """
    return tier_rank(requested_tier) <= tier_rank(authorized_tier)


@dataclass
class TierClassification:
    """The result of classifying a system or activity."""
    tier: str
    modifiers: list[str] = field(default_factory=list)
    triggered_overrides: list[str] = field(default_factory=list)
    assessment: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    uncertainty: str = "moderate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "modifiers": list(self.modifiers),
            "triggered_overrides": list(self.triggered_overrides),
            "assessment": dict(self.assessment),
            "rationale": self.rationale,
            "uncertainty": self.uncertainty,
        }

    def label(self) -> str:
        """The full tier label, e.g. 'T2-A/D'."""
        base = self.tier
        if self.modifiers:
            base += "-" + "/".join(sorted(self.modifiers))
        return base


def classify(
    consequence_overrides: list[str],
    *,
    assessment: dict[str, str] | None = None,
    modifiers: list[str] | None = None,
    uncertainty: str = "moderate",
) -> TierClassification:
    """Classify a system or activity using TADR Stage A + Stage B.

    Stage A: if any override in consequence_overrides matches a T3 override,
    classify as T3. Else if any matches a T2 override, classify as at least T2.
    Stage B: structured assessment can escalate (never de-escalate below the
    override floor).

    The highest credible consequence carries more weight than the most likely
    minor consequence.
    """
    assessment = assessment or {}
    modifiers = list(modifiers or [])
    invalid = validate_modifiers(modifiers)
    if invalid:
        raise ValueError(f"invalid TADR modifiers: {invalid}")

    triggered = [o for o in consequence_overrides]
    tier = "T1"  # floor

    # Stage A: consequence overrides
    for override in consequence_overrides:
        if override in T3_OVERRIDES:
            tier = "T3"
            break
    if tier != "T3":
        for override in consequence_overrides:
            if override in T2_OVERRIDES:
                tier = "T2"
                break

    # Stage B: structured assessment can escalate, not de-escalate
    magnitude = assessment.get("consequence_magnitude", "")
    if magnitude in ("catastrophic", "national", "global") and tier_rank(tier) < 3:
        tier = "T3"
    elif magnitude in ("severe", "regional") and tier_rank(tier) < 2:
        tier = "T2"

    autonomy = assessment.get("autonomy", "")
    if autonomy == "uncontrolled" and tier_rank(tier) < 3:
        tier = "T3"

    reversibility = assessment.get("reversibility", "")
    if reversibility == "irreversible" and tier_rank(tier) < 3:
        tier = "T3"

    return TierClassification(
        tier=tier, modifiers=modifiers, triggered_overrides=triggered,
        assessment=assessment, uncertainty=uncertainty,
        rationale=f"Classified {tier} via Stage A overrides + Stage B assessment",
    )
