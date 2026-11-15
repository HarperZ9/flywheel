"""Honesty boundary for optimization receipts: no quantum / hardware overclaim.

Harvest of dogfood pass 0086. The receipt may only assert a hardware execution
if a hardware solver branch actually completed, and may only assert a quantum
advantage if it also asserts a hardware execution. A toy exact/NOT_RUN solve
claims neither -- the same no-overreach-without-disclosure gate the visual
calibration boundary and research formal block enforce.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown

BOUNDARY_FIELDS = {"quantum_advantage_claim", "hardware_execution_claim"}


def validate_boundary(value: Any, solver: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.boundary", "expected object"))
        return
    reject_unknown(value, "$.boundary", BOUNDARY_FIELDS, issues)
    for flag in ("quantum_advantage_claim", "hardware_execution_claim"):
        if not isinstance(value.get(flag), bool):
            issues.append(Issue(f"$.boundary.{flag}", "expected boolean"))
    method = solver.get("method") if isinstance(solver, dict) else None
    status = solver.get("status") if isinstance(solver, dict) else None
    hardware_completed = method == "hardware" and status == "COMPLETED"
    if value.get("hardware_execution_claim") is True and not hardware_completed:
        issues.append(
            Issue(
                "$.boundary",
                "a hardware_execution_claim requires a COMPLETED hardware solver branch",
            )
        )
    if (
        value.get("quantum_advantage_claim") is True
        and value.get("hardware_execution_claim") is not True
    ):
        issues.append(
            Issue(
                "$.boundary",
                "a quantum_advantage_claim requires a hardware_execution_claim",
            )
        )
