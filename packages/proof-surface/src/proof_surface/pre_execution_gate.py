"""Pre-execution gate: a default-deny, fail-closed, ADVISORY mediation layer.

Given a planned action, its authorization receipt, an available budget, optional
observed state, and optional human-gap evidence, this gate returns a
GateDecision that a runtime or operator MUST enforce.  The gate REPORTS a
decision; it NEVER grants authority and is NEVER injected into a model as
trusted state.

Design principles
-----------------
* Default-deny: allow ONLY if every applicable check positively passes.
* Fail-closed on unknown: any dimension that cannot be positively confirmed
  collapses to needs-human, never to allow.
* Advisory-not-authority: the caller is responsible for enforcement; the gate
  produces a structured recommendation, not an execution capability.
* Forbidden-field guard applied recursively at every object level of the full
  request (same set as authorization-receipt and work-record, same mechanism).

Decision aggregation
--------------------
  allow        -- authorization=pass AND budget in {pass,not-applicable}
                 AND state in {pass,not-applicable}
                 AND human_gap in {pass,not-applicable}
  deny         -- any check is "fail"
  needs-human  -- no "fail", but at least one check is "unknown"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ._validate import Issue, reject_unknown, require_text
from .authorization_receipt import (
    FORBIDDEN_FIELDS,
    check_action,
    validate_authorization_receipt,
)
from .human_gap import check_human_gap, validate_human_gap
from .witness_receipt import WITNESS_VERDICTS

GATE_VERSION = "0.1"

# Check-result lattice values.
PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"
NOT_APPLICABLE = "not-applicable"
CHECK_VALUES = {PASS, FAIL, UNKNOWN, NOT_APPLICABLE}

# Final decision values.
ALLOW = "allow"
DENY = "deny"
NEEDS_HUMAN = "needs-human"
DECISION_VALUES = {ALLOW, DENY, NEEDS_HUMAN}

# Witness verdicts relevant to the state check.  The full closed lattice is
# imported from witness_receipt (single source of truth) so a legitimate EMET
# receipt carrying COHERENT / CORROBORATED / VIEW_DIFFERS_FROM_SOURCE /
# QUARANTINE_READ_PATH_DIVERGENCE is not rejected as structurally invalid.
WITNESS_MATCH = "MATCH"
WITNESS_DRIFT = "DRIFT"
WITNESS_UNVERIFIABLE = "UNVERIFIABLE"
WITNESS_COHERENT = "COHERENT"
WITNESS_CORROBORATED = "CORROBORATED"
WITNESS_VIEW_DIFFERS = "VIEW_DIFFERS_FROM_SOURCE"
WITNESS_QUARANTINE = "QUARANTINE_READ_PATH_DIVERGENCE"
# Verdicts that positively confirm state (PASS); everything else denies or escalates.
WITNESS_CONFIRMING = {WITNESS_MATCH, WITNESS_COHERENT, WITNESS_CORROBORATED}

# Hex digest pattern: exactly 64 lowercase hex characters.
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# Gate-request top-level field allowlist.
ROOT_FIELDS = {"planned_action", "authorization", "budget", "state", "human_gap"}

# Nested field allowlists.
PLANNED_ACTION_FIELDS = {"action_kind", "target", "estimated_cost"}
ESTIMATED_COST_FIELDS = {"tokens", "wall_ms"}
BUDGET_FIELDS = {"remaining_tokens", "remaining_wall_ms", "remaining_actions"}
STATE_FIELDS = {"witness_verdict", "target_digest", "expected_digest"}


# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """The gate's advisory output.

    decision  -- one of "allow", "deny", "needs-human".
    reasons   -- ordered list of human-readable strings explaining the decision.
    checks    -- per-dimension result; each value in {pass,fail,unknown,not-applicable}.
                Keys: "authorization", "budget", "state", "human_gap".
    """

    decision: str
    reasons: list[str]
    checks: dict[str, str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_gate_request(data: Any) -> list[Issue]:
    """Validate a gate-request object.  Returns [] iff structurally valid.

    This validates shape only (additionalProperties:false at every level,
    required fields present, types correct, forbidden-field guard recursive).
    It does NOT run the authorization or budget checks.
    """
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden_recursive(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)

    _validate_planned_action(data.get("planned_action"), issues)
    _validate_authorization_field(data.get("authorization"), issues)
    _validate_budget(data.get("budget"), issues)
    _validate_state(data.get("state"), issues)
    validate_human_gap(data.get("human_gap"), issues)

    return issues


def evaluate_gate(request: dict[str, Any]) -> GateDecision:
    """Evaluate the gate for a planned action request.

    Returns a GateDecision(decision, reasons, checks).  The caller MUST enforce
    the decision; this function is advisory only.

    Default-deny: returns DENY unless every applicable check returns pass.
    Fail-closed: any unknown dimension yields needs-human, never allow.
    """
    # --- Structural validation first -------------------------------------------
    shape_issues = validate_gate_request(request)
    if shape_issues:
        return GateDecision(
            decision=DENY,
            reasons=[
                "gate request is structurally invalid",
                *[f"{i.path}: {i.message}" for i in shape_issues],
            ],
            checks={
                "authorization": FAIL,
                "budget": NOT_APPLICABLE,
                "state": NOT_APPLICABLE,
                "human_gap": NOT_APPLICABLE,
            },
        )

    planned = request["planned_action"]
    action_kind: str = planned["action_kind"]
    target: str = planned["target"]
    estimated_cost: dict[str, Any] = planned.get("estimated_cost") or {}

    authorization_obj: dict[str, Any] = request.get("authorization") or {}
    budget_obj: dict[str, Any] = request.get("budget") or {}
    state_obj: dict[str, Any] | None = request.get("state")  # optional
    human_gap_obj: dict[str, Any] | None = request.get("human_gap")  # optional

    reasons: list[str] = []

    # --- Check: authorization --------------------------------------------------
    auth_check, auth_reasons = _check_authorization(
        authorization_obj, action_kind, target
    )
    reasons.extend(auth_reasons)

    # --- Check: budget ---------------------------------------------------------
    budget_check, budget_reasons = _check_budget(estimated_cost, budget_obj)
    reasons.extend(budget_reasons)

    # --- Check: state ----------------------------------------------------------
    state_check, state_reasons = _check_state(state_obj)
    reasons.extend(state_reasons)

    # --- Check: human gap ------------------------------------------------------
    human_gap_check, human_gap_reasons = check_human_gap(human_gap_obj)
    reasons.extend(human_gap_reasons)

    checks = {
        "authorization": auth_check,
        "budget": budget_check,
        "state": state_check,
        "human_gap": human_gap_check,
    }

    # --- Final aggregation (default-deny, fail-closed) -------------------------
    if any(v == FAIL for v in checks.values()):
        decision = DENY
        if not reasons:
            reasons = ["one or more checks failed"]
    elif any(v == UNKNOWN for v in checks.values()):
        decision = NEEDS_HUMAN
        if not reasons:
            reasons = ["one or more checks could not be positively confirmed"]
    else:
        # All checks are pass or not-applicable.
        decision = ALLOW
        reasons = ["all applicable checks passed"]

    return GateDecision(decision=decision, reasons=reasons, checks=checks)


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------


def _check_authorization(
    authorization: dict[str, Any],
    action_kind: str,
    target: str,
) -> tuple[str, list[str]]:
    """Run validate + check_action on the authorization receipt.

    Returns (check_result, reasons).
    """
    # Validate structure first.
    struct_issues = validate_authorization_receipt(authorization)
    if struct_issues:
        first = struct_issues[0]
        return FAIL, [
            f"invalid authorization: {first.path} -- {first.message}",
        ]

    # Structural validity confirmed; now check the specific action.
    denial = check_action(authorization, action_kind, target)
    if denial is not None:
        return FAIL, [f"authorization denied: {denial.message}"]

    return PASS, []


def _check_budget(
    estimated_cost: dict[str, Any],
    budget: dict[str, Any],
) -> tuple[str, list[str]]:
    """Check estimated cost against available budget.

    Dimensions: tokens, wall_ms.
    remaining_actions is also checked as a gate (>0 required if present).

    Rules per dimension (cost_field, remaining_field):
      - estimated present, remaining present, estimated > remaining -> FAIL
      - estimated present, remaining ABSENT -> UNKNOWN (never auto-allow)
      - estimated absent -> that dimension is not checked
    remaining_actions present and <= 0 -> FAIL (no actions left).
    No estimated_cost keys at all -> NOT_APPLICABLE.
    """
    if not estimated_cost:
        # remaining_actions alone can still gate.
        if "remaining_actions" in budget:
            ra = budget["remaining_actions"]
            if isinstance(ra, (int, float)) and not isinstance(ra, bool):
                if ra <= 0:
                    return FAIL, [
                        "budget denied: remaining_actions is 0 or negative -- no budget remaining"
                    ]
        return NOT_APPLICABLE, []

    reasons: list[str] = []
    result = PASS

    # Per-dimension cost checks.
    dimension_map = [
        ("tokens", "remaining_tokens"),
        ("wall_ms", "remaining_wall_ms"),
    ]
    for cost_key, budget_key in dimension_map:
        estimated = estimated_cost.get(cost_key)
        if estimated is None:
            continue  # Dimension not estimated; skip.
        remaining = budget.get(budget_key)
        if remaining is None:
            # Estimated cost given, but no remaining budget -- cannot confirm.
            reasons.append(
                f"budget unknown: estimated {cost_key}={estimated} but {budget_key} is absent -- cannot confirm budget"
            )
            if result != FAIL:
                result = UNKNOWN
        else:
            if estimated > remaining:
                reasons.append(
                    f"budget denied: estimated {cost_key}={estimated} exceeds remaining {remaining}"
                )
                result = FAIL

    # remaining_actions check (independent of estimated_cost keys).
    if "remaining_actions" in budget:
        ra = budget["remaining_actions"]
        if isinstance(ra, (int, float)) and not isinstance(ra, bool):
            if ra <= 0:
                reasons.append(
                    "budget denied: remaining_actions is 0 or negative -- no budget remaining"
                )
                result = FAIL

    if result == PASS:
        return PASS, []
    return result, reasons


def _check_state(
    state: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Check optional observed state.

    If state is absent -> NOT_APPLICABLE (does not block).
    witness_verdict DRIFT -> FAIL/deny.
    witness_verdict UNVERIFIABLE -> UNKNOWN/needs-human.
    target_digest != expected_digest (both present) -> FAIL/deny.
    """
    if state is None:
        return NOT_APPLICABLE, []

    reasons: list[str] = []
    result = PASS

    verdict = state.get("witness_verdict")
    if verdict is not None:
        if verdict in WITNESS_CONFIRMING:
            pass  # positive confirmation -- leaves result at PASS
        elif verdict == WITNESS_DRIFT:
            reasons.append(
                "state denied: witness_verdict is DRIFT -- target has drifted from expected state"
            )
            result = FAIL
        elif verdict == WITNESS_VIEW_DIFFERS:
            reasons.append(
                "state denied: witness_verdict is VIEW_DIFFERS_FROM_SOURCE -- view does not match source"
            )
            result = FAIL
        elif verdict == WITNESS_QUARANTINE:
            reasons.append(
                "state denied: witness_verdict is QUARANTINE_READ_PATH_DIVERGENCE -- read path is quarantined"
            )
            result = FAIL
        elif verdict == WITNESS_UNVERIFIABLE:
            reasons.append(
                "state unknown: witness_verdict is UNVERIFIABLE -- cannot confirm target state"
            )
            if result != FAIL:
                result = UNKNOWN

    target_digest = state.get("target_digest")
    expected_digest = state.get("expected_digest")
    if (target_digest is None) != (expected_digest is None):
        # Exactly one digest present: an observed digest with nothing to compare
        # against (or vice versa) cannot positively confirm integrity. Fail-closed
        # to UNKNOWN (-> needs-human), never a silent PASS.
        reasons.append(
            "state unknown: exactly one of target_digest/expected_digest is present -- cannot confirm integrity"
        )
        if result != FAIL:
            result = UNKNOWN
    elif target_digest is not None and expected_digest is not None:
        if target_digest != expected_digest:
            reasons.append(
                "state denied: target_digest does not match expected_digest -- integrity check failed"
            )
            result = FAIL

    if result == PASS:
        return PASS, []
    return result, reasons


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _reject_forbidden_recursive(node: Any, path: str, issues: list[Issue]) -> None:
    """Recursively reject any key whose name is in FORBIDDEN_FIELDS (same set as
    authorization-receipt and work-record -- permanent, fail-closed guard)."""
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden_recursive(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden_recursive(item, f"{path}[{index}]", issues)


def _validate_planned_action(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.planned_action", "expected object"))
        return
    reject_unknown(value, "$.planned_action", PLANNED_ACTION_FIELDS, issues)
    require_text(value, "action_kind", issues, "$.planned_action.action_kind")
    require_text(value, "target", issues, "$.planned_action.target")
    _validate_estimated_cost(value.get("estimated_cost"), issues)


def _validate_estimated_cost(value: Any, issues: list[Issue]) -> None:
    if value is None:
        return  # optional
    if not isinstance(value, dict):
        issues.append(Issue("$.planned_action.estimated_cost", "expected object"))
        return
    reject_unknown(
        value, "$.planned_action.estimated_cost", ESTIMATED_COST_FIELDS, issues
    )
    for field_name in ("tokens", "wall_ms"):
        if field_name in value:
            v = value[field_name]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                issues.append(
                    Issue(
                        f"$.planned_action.estimated_cost.{field_name}",
                        "expected non-negative number",
                    )
                )


def _validate_authorization_field(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(
            Issue("$.authorization", "expected object (authorization-receipt)")
        )
        return
    # Structural validation is deferred to evaluate_gate; here we only verify
    # it is an object so the field guard and reject_unknown can run.


def _validate_budget(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.budget", "expected object"))
        return
    reject_unknown(value, "$.budget", BUDGET_FIELDS, issues)
    for field_name in ("remaining_tokens", "remaining_wall_ms", "remaining_actions"):
        if field_name in value:
            v = value[field_name]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                issues.append(
                    Issue(
                        f"$.budget.{field_name}",
                        "expected non-negative number",
                    )
                )


def _validate_state(value: Any, issues: list[Issue]) -> None:
    if value is None:
        return  # optional
    if not isinstance(value, dict):
        issues.append(Issue("$.state", "expected object"))
        return
    reject_unknown(value, "$.state", STATE_FIELDS, issues)
    verdict = value.get("witness_verdict")
    if verdict is not None and verdict not in WITNESS_VERDICTS:
        choices = ", ".join(sorted(WITNESS_VERDICTS))
        issues.append(Issue("$.state.witness_verdict", f"expected one of: {choices}"))
    for digest_field in ("target_digest", "expected_digest"):
        if digest_field in value:
            dv = value[digest_field]
            if not isinstance(dv, str) or not _HEX64_RE.match(dv):
                issues.append(
                    Issue(
                        f"$.state.{digest_field}",
                        "expected 64-char lowercase hex digest",
                    )
                )
    # A digest is only meaningful as a pair (observed vs expected); reject a
    # half-pair structurally so it can never reach the check layer.
    if ("target_digest" in value) != ("expected_digest" in value):
        issues.append(
            Issue(
                "$.state",
                "target_digest and expected_digest must appear together or not at all",
            )
        )
