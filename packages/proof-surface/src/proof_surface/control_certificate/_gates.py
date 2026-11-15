"""Control-certificate gates: a stability claim must be able to fail.

Harvest of dogfood passes 0112/0113 plus the operator's robotics/cybernetics
lane. Three load-bearing honesty rules: (1) the packet must carry a negative
fixture that PROVABLY violates the certificate (a checker that cannot fail on
a known-unstable system is not a checker); (2) a certificate kind must witness
ALL of its required conditions (a lyapunov claim without a witnessed decrease
is an assertion, not a certificate); (3) the sim-to-real boundary: hardware
validity is never claimable from simulation-only evidence.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown, require_text

NEGATIVE_FIXTURE_FIELDS = {
    "description",
    "condition",
    "residual",
    "tolerance",
    "violates_certificate",
}
SIM_TO_REAL_FIELDS = {"hardware_validity_claim", "hardware_evidence"}

CONDITION_KINDS = {
    "positive-definite",
    "decrease",
    "invariance",
    "well-founded",
    "contraction",
    "recursive-feasibility",
    "constraint-satisfaction",
}

REQUIRED_CONDITIONS = {
    "lyapunov": {"positive-definite", "decrease"},
    "ranking-function": {"well-founded", "decrease"},
    "contraction-metric": {"contraction"},
    "mpc-feasibility": {"recursive-feasibility", "constraint-satisfaction"},
}

HARDWARE_REGIMES = {"hardware", "hybrid"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_negative_fixture(value: Any, issues: list[Issue]) -> None:
    """A required negative fixture that must genuinely violate the certificate."""
    path = "$.negative_fixture"
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object (a required violating fixture)"))
        return
    reject_unknown(value, path, NEGATIVE_FIXTURE_FIELDS, issues)
    require_text(value, "description", issues, f"{path}.description")
    condition = value.get("condition")
    if condition not in CONDITION_KINDS:
        issues.append(
            Issue(f"{path}.condition", "expected a known certificate condition")
        )
    residual = value.get("residual")
    tolerance = value.get("tolerance")
    if not _is_number(residual) or residual < 0:
        issues.append(Issue(f"{path}.residual", "expected a non-negative number"))
    if not _is_number(tolerance) or tolerance <= 0:
        issues.append(Issue(f"{path}.tolerance", "expected a number > 0"))
    if value.get("violates_certificate") is not True:
        issues.append(
            Issue(
                f"{path}.violates_certificate",
                "expected true -- a certificate check must include a negative fixture "
                "that provably violates it (else it has no discriminating power)",
            )
        )
    elif _is_number(residual) and _is_number(tolerance) and residual <= tolerance:
        issues.append(
            Issue(
                path,
                "violates_certificate is true but the residual is within tolerance -- "
                "the negative fixture does not actually violate the certificate",
            )
        )


def validate_kind_completeness(
    kind: Any, witnesses: Any, issues: list[Issue]
) -> None:
    """A claimed certificate kind must witness all of its required conditions."""
    required = REQUIRED_CONDITIONS.get(kind)
    if required is None or not isinstance(witnesses, list):
        return
    witnessed = {
        w.get("condition")
        for w in witnesses
        if isinstance(w, dict) and w.get("condition") in CONDITION_KINDS
    }
    missing = sorted(required - witnessed)
    if missing:
        issues.append(
            Issue(
                "$.witnesses",
                f"certificate kind '{kind}' requires witnessed condition(s) "
                f"{', '.join(missing)} -- a certificate claim without its defining "
                "conditions witnessed is an assertion",
            )
        )


def validate_sim_to_real(value: Any, regime: Any, issues: list[Issue]) -> None:
    """The sim-to-real boundary: hardware validity needs hardware evidence."""
    path = "$.sim_to_real"
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object (a required disclosed boundary)"))
        return
    reject_unknown(value, path, SIM_TO_REAL_FIELDS, issues)
    claim = value.get("hardware_validity_claim")
    if not isinstance(claim, bool):
        issues.append(Issue(f"{path}.hardware_validity_claim", "expected boolean"))
        return
    evidence = value.get("hardware_evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        issues.append(
            Issue(f"{path}.hardware_evidence", "expected array of non-empty strings")
        )
        return
    if not claim:
        return
    if regime not in HARDWARE_REGIMES:
        issues.append(
            Issue(
                f"{path}.hardware_validity_claim",
                "simulation-only evidence cannot claim hardware validity -- verified "
                "in sim is not verified on hardware",
            )
        )
    if not evidence:
        issues.append(
            Issue(
                f"{path}.hardware_evidence",
                "a hardware validity claim requires hardware evidence references",
            )
        )
