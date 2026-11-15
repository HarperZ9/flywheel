"""Shared evidence-class independence contract (dogfood 0126).

A packet may declare the classes of evidence behind its claim, from a closed
vocabulary. The gate: a fact-tier promotion requires at least one class that is
not single-modality-derived, and evidence that is entirely single-modality
caps the promotion at the hypothesis rung -- one modality talking to itself
can raise a hypothesis, never establish a fact. Optional and stdlib-only; a
packet without the field validates unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping

from ._validate import Issue

EVIDENCE_CLASSES = {
    "primary-source",
    "independent-replication",
    "executable-check",
    "human-review",
    "single-modality-derived",
}
SINGLE_MODALITY_CLASS = "single-modality-derived"


def validate_evidence_classes(
    value: Any, issues: list[Issue], path: str = "$.evidence_classes"
) -> None:
    """Validate the optional evidence_classes list. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, list) or not value:
        issues.append(
            Issue(path, "expected non-empty array (declared means disclosed)")
        )
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if item not in EVIDENCE_CLASSES:
            choices = ", ".join(sorted(EVIDENCE_CLASSES))
            issues.append(Issue(item_path, f"expected one of: {choices}"))
            continue
        if item in seen:
            issues.append(Issue(item_path, "duplicate evidence class"))
        seen.add(item)


def has_independent_class(value: Any) -> bool:
    """True iff at least one declared class is not single-modality-derived."""
    return isinstance(value, list) and any(
        item in EVIDENCE_CLASSES and item != SINGLE_MODALITY_CLASS for item in value
    )


def enforce_evidence_independence(
    value: Any,
    promotion: Any,
    rung_rank: Mapping[str, int],
    cap_rank: int,
    issues: list[Issue],
    promotion_path: str = "$.promotion",
) -> None:
    """Cap an all-single-modality packet at cap_rank (the hypothesis rung).

    Fires only when evidence_classes is declared and carries no independent
    class. Off-ladder rungs (absent from rung_rank) claim no achievement and
    are never capped.
    """
    if not isinstance(value, list) or not value or has_independent_class(value):
        return
    rank = rung_rank.get(promotion) if isinstance(promotion, str) else None
    if rank is None or rank <= cap_rank:
        return
    issues.append(
        Issue(
            promotion_path,
            f"promotion {promotion!r} requires at least one evidence class that "
            "is not single-modality-derived; single-modality evidence caps at "
            "the hypothesis rung",
        )
    )
