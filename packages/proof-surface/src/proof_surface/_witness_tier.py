"""Shared witness-tier contract: no tier inflation.

A packet may declare the verifier tier it targeted, the strongest tier that
actually executed, and whether the target slot ran (the dogfood prover-branch
precedent). The closed tier order maps 1:1 onto the positive rungs of the
research_claim promotion ladder. The gate: a promotion rung above the
strongest executed tier's mapping is unwitnessed and rejected -- when the
target slot did not execute (tool unavailable or fenced), the declared target
tier was not achieved. Optional and stdlib-only; a packet without the field
validates unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping

from ._validate import Issue, reject_unknown, require_enum

# Closed verifier-tier order, weakest to strongest. The rank doubles as the
# highest promotion-ladder rank that tier can witness (see research_claim's
# RUNG_RANK, bound 1:1).
VERIFIER_TIERS = {
    "none": 0,
    "manual-review": 1,
    "symbolic-check": 2,
    "numeric-probe": 3,
    "crucible-rederivation": 4,
    "kernel-proof": 5,
}

TARGET_SLOT_STATUSES = {
    "EXECUTED",
    "NOT_EXECUTED_TOOL_UNAVAILABLE",
    "NOT_EXECUTED_FENCED",
}
WITNESS_TIER_FIELDS = {
    "declared_target_verifier",
    "strongest_executed_tier",
    "target_slot_status",
}


def validate_witness_tier(
    value: Any, issues: list[Issue], path: str = "$.witness_tier"
) -> None:
    """Validate the optional witness_tier object. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, WITNESS_TIER_FIELDS, issues)
    tiers = set(VERIFIER_TIERS)
    require_enum(
        value,
        "declared_target_verifier",
        tiers,
        issues,
        f"{path}.declared_target_verifier",
    )
    require_enum(
        value,
        "strongest_executed_tier",
        tiers,
        issues,
        f"{path}.strongest_executed_tier",
    )
    require_enum(
        value,
        "target_slot_status",
        TARGET_SLOT_STATUSES,
        issues,
        f"{path}.target_slot_status",
    )
    target_rank = VERIFIER_TIERS.get(value.get("declared_target_verifier"))
    executed_rank = VERIFIER_TIERS.get(value.get("strongest_executed_tier"))
    if (
        value.get("target_slot_status") == "EXECUTED"
        and target_rank is not None
        and executed_rank is not None
        and executed_rank < target_rank
    ):
        issues.append(
            Issue(
                f"{path}.strongest_executed_tier",
                "an EXECUTED target slot whose strongest executed tier is below "
                "the declared target is a contradiction",
            )
        )


def enforce_no_tier_inflation(
    value: Any,
    promotion: Any,
    rung_rank: Mapping[str, int],
    issues: list[Issue],
    promotion_path: str = "$.promotion",
) -> None:
    """Cap the promotion rung at the strongest executed tier's rung mapping.

    Off-ladder rungs (absent from rung_rank) claim no achievement and are
    never capped. A structurally broken witness_tier is reported by
    validate_witness_tier; this gate only fires on a known tier.
    """
    if not isinstance(value, dict):
        return
    cap = VERIFIER_TIERS.get(value.get("strongest_executed_tier"))
    rank = rung_rank.get(promotion) if isinstance(promotion, str) else None
    if cap is None or rank is None or rank <= cap:
        return
    issues.append(
        Issue(
            promotion_path,
            f"promotion {promotion!r} exceeds the strongest executed verifier "
            f"tier {value.get('strongest_executed_tier')!r} (no tier inflation: "
            "a rung above what actually ran is unwitnessed)",
        )
    )
