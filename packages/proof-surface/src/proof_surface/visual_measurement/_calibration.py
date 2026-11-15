"""Calibration boundary: a read-only color surface may not claim a physical calibration.

Harvest of dogfood pass 0081. `read_only=true` stops mutation, but nothing stopped
the packet text from claiming a display was physically calibrated. This makes the
anti-overclaim machine-checkable.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown

CALIBRATION_BOUNDARY_FIELDS = {
    "hardware_measurement_used",
    "physical_calibration_claim",
    "instrument",
    "mutation_evidence",
}


def validate_calibration_boundary(
    value: Any, read_only: Any, issues: list[Issue]
) -> None:
    """A physical-calibration claim must fully disclose hardware + mutation.

    A read-only color surface never touched the display, so it may not claim a
    physical calibration. The claim is admissible only if it discloses a hardware
    measurement, the instrument, mutation evidence, AND a non-read-only packet.
    """
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue("$.calibration_boundary", "expected object"))
        return
    reject_unknown(value, "$.calibration_boundary", CALIBRATION_BOUNDARY_FIELDS, issues)
    for flag in ("hardware_measurement_used", "physical_calibration_claim"):
        if not isinstance(value.get(flag), bool):
            issues.append(Issue(f"$.calibration_boundary.{flag}", "expected boolean"))
    instrument = value.get("instrument")
    if instrument is not None and (
        not isinstance(instrument, str) or not instrument.strip()
    ):
        issues.append(
            Issue(
                "$.calibration_boundary.instrument", "expected non-empty string or null"
            )
        )
    evidence = value.get("mutation_evidence")
    if evidence is not None:
        _validate_evidence(evidence, issues)
    if value.get("physical_calibration_claim") is True and not (
        value.get("hardware_measurement_used") is True
        and isinstance(instrument, str)
        and instrument.strip()
        and isinstance(evidence, list)
        and evidence
        and read_only is not True
    ):
        issues.append(
            Issue(
                "$.calibration_boundary",
                "a physical_calibration_claim must disclose hardware_measurement_used, "
                "an instrument, mutation_evidence, and a non-read-only packet",
            )
        )


def _validate_evidence(evidence: Any, issues: list[Issue]) -> None:
    if not isinstance(evidence, list):
        issues.append(
            Issue("$.calibration_boundary.mutation_evidence", "expected array")
        )
        return
    for index, item in enumerate(evidence):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                Issue(
                    f"$.calibration_boundary.mutation_evidence[{index}]",
                    "expected non-empty string",
                )
            )
