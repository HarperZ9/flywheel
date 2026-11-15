"""Evaluation contract: evaluation as a deploy gate, not a vanity score.

An evaluation contract records the objective, measurable criteria, and
direction of an evaluation run.  The ``evaluate`` function compares actual
measured results against those criteria and returns a structured
EvalDecision.

Design principles
-----------------
* Advisory-never-authority: EvalDecision REPORTS a recommendation.  The
  runtime or operator is the enforcement point.  This contract never grants
  authority and is never injected into a model as trusted state.
* Default-deny / uncertainty-block: deploy ONLY if every required criterion
  passes.  Any required criterion that is uncertain (measured value straddles
  the threshold under uncertainty) or missing escalates to needs-human.
  Never deploy on uncertainty.
* Forbidden-field guard: the same 16-key FORBIDDEN_FIELDS set used by every
  other proof-surface contract is applied recursively and fail-closed.
* additionalProperties:false at every object level.
* Closed enums for direction and EvalDecision.decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._validate import Issue, reject_unknown, require_const, require_enum, require_text

EVAL_VERSION = "0.1"

# Top-level field allowlist.
ROOT_FIELDS = {
    "eval_version",
    "contract_id",
    "objective",
    "criteria",
    "notes",
}

# Criterion field allowlist.
CRITERION_FIELDS = {"name", "metric", "threshold", "direction", "required"}

# Closed enum for comparison direction.
DIRECTIONS = {">=", "<="}

# Decision outcomes -- closed enum.
DECISIONS = {"deploy", "block", "needs-human"}

# Field NAMES lifted verbatim from the excluded warden-prefire capsule/meta.
# Identical set to every other proof-surface contract.  Applied recursively;
# fail-closed.
FORBIDDEN_FIELDS = {
    "federal_appointment",
    "oversight_principals",
    "operator_role",
    "judgment_owner",
    "proof_policy",
    "policy_boundary",
    "authorization_context_mode",
    "model_authorization_behavior",
    "guardrail_posture",
    "consume_verified_native_state",
    "lossy_neutral_embedded_state",
    "sovereignty_capsule",
    "self_applicable",
    "recursion_depth",
    "prefire",
    "run_state",
}


# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalDecision:
    """Advisory output of evaluate().

    decision       -- one of "deploy", "block", "needs-human".
    reasons        -- ordered list of human-readable strings.
    per_criterion  -- mapping of criterion name -> "pass"|"fail"|"uncertain"|"missing".
    """

    decision: str
    reasons: list[str]
    per_criterion: dict[str, str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_evaluation_contract(data: Any) -> list[Issue]:
    """Validate an evaluation-contract document.  Returns [] iff valid."""
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "eval_version", EVAL_VERSION, issues)
    require_text(data, "contract_id", issues)
    require_text(data, "objective", issues)
    _validate_criteria(data.get("criteria"), issues)
    _validate_notes(data.get("notes"), issues)
    return issues


def evaluate(contract: dict[str, Any], results: list[dict[str, Any]]) -> EvalDecision:
    """Compare measured results against the contract's criteria.

    results items: { name (str), measured (number), uncertainty? (>=0, default 0) }

    Per-criterion verdict:
      "pass"      -- criterion satisfied (direction check clears with no straddle)
      "fail"      -- criterion not satisfied (direction check fails outside uncertainty)
      "uncertain" -- [measured-uncertainty, measured+uncertainty] straddles threshold
      "missing"   -- no result entry found for this criterion name

    Aggregation rule (default-deny, never deploy on uncertainty):
      deploy      -- every required criterion is "pass"
      block       -- any required criterion is "fail"
      needs-human -- no required "fail", but at least one required criterion is
                    "uncertain" or "missing"

    The contract is structurally validated first (mirroring evaluate_gate /
    check_action / verify_delegation): an invalid contract returns ``block``
    rather than being processed, so an empty/missing criteria list or a tampered
    direction can never silently yield ``deploy`` (default-deny / fail-closed).
    """
    issues = validate_evaluation_contract(contract)
    if issues:
        return EvalDecision(
            decision="block",
            reasons=[f"contract invalid: {issues[0].path} -- {issues[0].message}"],
            per_criterion={},
        )

    criteria: list[dict[str, Any]] = contract.get("criteria", [])

    # Build a lookup from result name -> result dict.
    result_map: dict[str, dict[str, Any]] = {}
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("name"), str):
            result_map[r["name"]] = r

    per_criterion: dict[str, str] = {}
    reasons: list[str] = []

    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        name: str = criterion.get("name", "")
        threshold: float = criterion.get("threshold", 0.0)
        direction: str = criterion.get("direction", ">=")
        required: bool = criterion.get("required", False)

        if name not in result_map:
            per_criterion[name] = "missing"
            if required:
                reasons.append(f"required criterion {name!r} has no result (missing)")
            continue

        result = result_map[name]
        measured = result.get("measured")
        uncertainty_raw = result.get("uncertainty", 0)

        # Coerce to float; treat non-numeric as uncertainty=0.
        try:
            measured_f = float(measured)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            per_criterion[name] = "missing"
            if required:
                reasons.append(
                    f"required criterion {name!r} has non-numeric measured value"
                )
            continue

        try:
            uncertainty_f = (
                float(uncertainty_raw) if uncertainty_raw is not None else 0.0
            )
        except (TypeError, ValueError):
            uncertainty_f = 0.0
        if uncertainty_f < 0:
            uncertainty_f = 0.0

        verdict = _compare(measured_f, uncertainty_f, threshold, direction)
        per_criterion[name] = verdict

        if required and verdict != "pass":
            reasons.append(
                f"required criterion {name!r}: measured={measured_f} "
                f"(±{uncertainty_f}) vs threshold={threshold} direction={direction!r} "
                f"-> {verdict}"
            )

    # Aggregate.
    required_verdicts = [
        per_criterion[c["name"]]
        for c in criteria
        if isinstance(c, dict) and c.get("required") and c.get("name") in per_criterion
    ]
    # Also count required criteria that are flat missing (never entered per_criterion
    # at all, which can happen if criterion.name is not a non-empty string -- unlikely
    # given schema, but guard anyway).
    for c in criteria:
        if not isinstance(c, dict):
            continue
        if c.get("required") and c.get("name", "") not in per_criterion:
            required_verdicts.append("missing")

    if any(v == "fail" for v in required_verdicts):
        decision = "block"
        if not reasons:
            reasons = ["one or more required criteria failed"]
    elif any(v in ("uncertain", "missing") for v in required_verdicts):
        decision = "needs-human"
        if not reasons:
            reasons = ["one or more required criteria are uncertain or missing"]
    else:
        decision = "deploy"
        reasons = ["all required criteria passed"]

    return EvalDecision(decision=decision, reasons=reasons, per_criterion=per_criterion)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compare(
    measured: float,
    uncertainty: float,
    threshold: float,
    direction: str,
) -> str:
    """Classify a single criterion result as pass/fail/uncertain.

    Uncertainty-aware:
      direction ">=" ->
        pass      if (measured - uncertainty) >= threshold
        fail      if (measured + uncertainty) <  threshold
        uncertain if the interval straddles (neither side fully clears)
      direction "<=" ->
        pass      if (measured + uncertainty) <= threshold
        fail      if (measured - uncertainty) >  threshold
        uncertain if the interval straddles
    """
    low = measured - uncertainty
    high = measured + uncertainty

    if direction == ">=":
        if low >= threshold:
            return "pass"
        if high < threshold:
            return "fail"
        return "uncertain"
    elif direction == "<=":
        if high <= threshold:
            return "pass"
        if low > threshold:
            return "fail"
        return "uncertain"
    else:
        # Unrecognized direction -- fail closed (default-deny). validate_*
        # rejects this upstream, but _compare must not silently pick a branch.
        return "fail"


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    """Recursively reject any key whose name appears in FORBIDDEN_FIELDS."""
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_criteria(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.criteria", "expected array"))
        return
    if len(value) == 0:
        issues.append(Issue("$.criteria", "expected at least one criterion"))
        return
    for index, item in enumerate(value):
        _validate_criterion(item, index, issues)


def _validate_criterion(item: Any, index: int, issues: list[Issue]) -> None:
    base = f"$.criteria[{index}]"
    if not isinstance(item, dict):
        issues.append(Issue(base, "expected object"))
        return
    reject_unknown(item, base, CRITERION_FIELDS, issues)
    # name
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(Issue(f"{base}.name", "expected non-empty string"))
    # metric
    metric = item.get("metric")
    if not isinstance(metric, str) or not metric.strip():
        issues.append(Issue(f"{base}.metric", "expected non-empty string"))
    # threshold
    threshold = item.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        issues.append(Issue(f"{base}.threshold", "expected number"))
    # direction
    require_enum(item, "direction", DIRECTIONS, issues, f"{base}.direction")
    # required
    required = item.get("required")
    if not isinstance(required, bool):
        issues.append(Issue(f"{base}.required", "expected boolean"))


def _validate_notes(value: Any, issues: list[Issue]) -> None:
    if value is not None and not isinstance(value, str):
        issues.append(Issue("$.notes", "expected string"))
