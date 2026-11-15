"""Compute-lease receipts: paid GPU / cluster work as an accountable external write.

Harvest of research/rl-scaling-receipt-spine.md Lane 3. A compute_lease may only
sit on an external or irreversible side-effect (a paid job mutates the world);
attaching one to a read is an error. Budget ref, queue id, and a typed terminal
status are required so a reviewer can reconcile paid compute after the fact.
"""

from __future__ import annotations

from typing import Any

from ._validate import Issue, reject_unknown, require_enum, require_text

COMPUTE_LEASE_FIELDS = {
    "budget_ref",
    "queue_id",
    "terminal_status",
    "external_request_id",
}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}
_LEASE_CLASSES = {"external", "irreversible"}


def validate_compute_lease(
    value: Any, side_effect_class: Any, path: str, issues: list[Issue]
) -> None:
    """Validate an optional compute_lease on a side-effect. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, COMPUTE_LEASE_FIELDS, issues)
    require_text(value, "budget_ref", issues, f"{path}.budget_ref")
    require_text(value, "queue_id", issues, f"{path}.queue_id")
    require_enum(
        value, "terminal_status", TERMINAL_STATUSES, issues, f"{path}.terminal_status"
    )
    external_request_id = value.get("external_request_id")
    if external_request_id is not None and (
        not isinstance(external_request_id, str) or not external_request_id.strip()
    ):
        issues.append(
            Issue(f"{path}.external_request_id", "expected non-empty string or null")
        )
    if side_effect_class not in _LEASE_CLASSES:
        issues.append(
            Issue(
                path,
                "a compute_lease requires an external or irreversible side-effect "
                f"(class is {side_effect_class!r})",
            )
        )
