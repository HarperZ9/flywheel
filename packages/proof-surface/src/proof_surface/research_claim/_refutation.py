"""Refutation gate: a standing counterexample outranks any fixture-level pass.

Harvest of the operator-supplied verification-frontier corpus. A decades-old
belief dies to one counterexample regardless of how many checks it passed, so a
packet holding a standing counterexample (a `refuted` attempt or
`formal.counterexample_found=true`) must sit on the REFUTED rung -- and REFUTED
may not be claimed without one. Companion gate: a kernel replay that PASSED with
unresolved `sorry` holes is not a proof.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue


def _formal(data: dict[str, Any]) -> dict[str, Any]:
    formal = data.get("formal")
    return formal if isinstance(formal, dict) else {}


def has_standing_counterexample(data: dict[str, Any]) -> bool:
    attempts = data.get("attempts")
    refuted = isinstance(attempts, list) and any(
        isinstance(a, dict) and a.get("result") == "refuted" for a in attempts
    )
    return refuted or _formal(data).get("counterexample_found") is True


def validate_refutation_gate(data: dict[str, Any], issues: list[Issue]) -> None:
    formal = _formal(data)
    _validate_formal_extras(formal, issues)
    sorries = formal.get("unresolved_sorry")
    if formal.get("compiled_replay_status") == "PASSED" and (
        sorries is True or (isinstance(sorries, int) and sorries > 0)
    ):
        issues.append(
            Issue(
                "$.formal.unresolved_sorry",
                "a PASSED kernel replay with unresolved sorry holes is not a proof",
            )
        )
    standing = has_standing_counterexample(data)
    promotion = data.get("promotion")
    if standing and promotion != "REFUTED":
        issues.append(
            Issue(
                "$.promotion",
                "a standing counterexample (refuted attempt or formal counterexample) "
                "forces promotion REFUTED -- passing checks do not outweigh it",
            )
        )
    elif promotion == "REFUTED" and not standing:
        issues.append(
            Issue(
                "$.promotion",
                "REFUTED requires a standing counterexample (a refuted attempt or "
                "formal.counterexample_found)",
            )
        )


def _validate_formal_extras(formal: dict[str, Any], issues: list[Issue]) -> None:
    sorries = formal.get("unresolved_sorry")
    if sorries is not None and not (
        isinstance(sorries, bool) or (isinstance(sorries, int) and sorries >= 0)
    ):
        issues.append(
            Issue(
                "$.formal.unresolved_sorry",
                "expected boolean or non-negative integer or null",
            )
        )
    found = formal.get("counterexample_found")
    if found is not None and not isinstance(found, bool):
        issues.append(
            Issue("$.formal.counterexample_found", "expected boolean or null")
        )
