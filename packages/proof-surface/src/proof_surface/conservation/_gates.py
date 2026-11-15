"""Conservation gate: a check must be able to fail on a known-bad input.

Harvest of dogfood passes 0105/0106/0107. The load-bearing honesty rule: a
conservation packet must carry a negative fixture that PROVABLY breaks the
declared invariant (drift beyond tolerance). A "check" whose negative fixture
does not break has no discriminating power -- a verifier that can't fail is not
a verifier.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown, require_text

NEGATIVE_FIXTURE_FIELDS = {"description", "drift", "tolerance", "breaks_invariant"}
BOUNDARY_FIXTURE_FIELDS = {"description", "goal_holds", "condition_holds"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_negative_fixture(value: Any, issues: list[Issue]) -> None:
    """A required negative fixture that must genuinely break the invariant."""
    path = "$.negative_fixture"
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object (a required breaking fixture)"))
        return
    reject_unknown(value, path, NEGATIVE_FIXTURE_FIELDS, issues)
    require_text(value, "description", issues, f"{path}.description")
    drift = value.get("drift")
    tolerance = value.get("tolerance")
    if not _is_number(drift) or drift < 0:
        issues.append(Issue(f"{path}.drift", "expected a non-negative number"))
    if not _is_number(tolerance) or tolerance <= 0:
        issues.append(Issue(f"{path}.tolerance", "expected a number > 0"))
    if value.get("breaks_invariant") is not True:
        issues.append(
            Issue(
                f"{path}.breaks_invariant",
                "expected true -- a conservation check must include a negative fixture "
                "that provably breaks the invariant (else it has no discriminating power)",
            )
        )
    elif _is_number(drift) and _is_number(tolerance) and drift <= tolerance:
        issues.append(
            Issue(
                path,
                "breaks_invariant is true but drift is within tolerance -- the negative "
                "fixture does not actually break the invariant",
            )
        )


def validate_boundary_fixture(value: Any, issues: list[Issue]) -> None:
    """Optional: proves the claimed condition is sufficient but NOT necessary.

    A boundary fixture must show the goal holding while the claimed condition
    fails (pass 0108: a stationary-but-not-reversible chain). That forbids a
    "condition <=> goal" overclaim when only "condition => goal" is witnessed.
    """
    if value is None:
        return
    path = "$.boundary_fixture"
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, BOUNDARY_FIXTURE_FIELDS, issues)
    require_text(value, "description", issues, f"{path}.description")
    for flag in ("goal_holds", "condition_holds"):
        if not isinstance(value.get(flag), bool):
            issues.append(Issue(f"{path}.{flag}", "expected boolean"))
    if value.get("goal_holds") is not True:
        issues.append(
            Issue(
                f"{path}.goal_holds",
                "a boundary fixture must show the goal HOLDING (else it is a negative "
                "case, not a sufficiency boundary)",
            )
        )
    if value.get("condition_holds") is not False:
        issues.append(
            Issue(
                f"{path}.condition_holds",
                "a boundary fixture must show the claimed condition FAILING, to prove "
                "the condition is sufficient but not necessary",
            )
        )
