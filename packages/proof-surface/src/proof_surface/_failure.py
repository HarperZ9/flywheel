"""Typed failure codes: negative signals are first-class, not prose.

Harvest of two research notes that independently demand the same primitive:
`rl-scaling-receipt-spine.md` ("typed failure codes instead of prose-only
failures") and `mycology-network-intelligence.md` ("keep negative signals
first-class: missing evidence, stale criteria, unjoinable action identity,
failed route, and unverifiable claims should have distinct codes").

A ``failure_labels`` entry MUST be one of these codes, so a downstream checker
can branch on the failure class deterministically instead of scraping prose.
Shared across the family; wired into the agent-action receipt first.
"""

from __future__ import annotations

from typing import Any

from ._validate import Issue

FAILURE_CODES = {
    "binding_failed",
    "unjoinable_action",
    "verification_unverifiable",
    "stale_criterion",
    "authority_gap",
    "evidence_gap",
    "duplicate_idempotency_key",
    "external_request_id_missing",
    "failed_route",
}


def validate_failure_labels(
    value: Any, issues: list[Issue], path: str = "$.failure_labels"
) -> None:
    """Validate an optional typed failure-code list. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, list):
        issues.append(Issue(path, "expected an array of typed failure codes"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or item not in FAILURE_CODES:
            issues.append(
                Issue(
                    f"{path}[{index}]",
                    f"expected a known failure code (one of {sorted(FAILURE_CODES)}); "
                    f"got {item!r}",
                )
            )
