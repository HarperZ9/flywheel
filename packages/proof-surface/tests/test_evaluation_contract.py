"""Tests for the evaluation-contract (Contract 4).

Contract invariants exercised:
  * Forbidden-field guard -- recursive, fail-closed, same 16-key set as all other
    proof-surface contracts.
  * additionalProperties:false at root and every nested criterion object.
  * Closed direction enum (">=" | "<=").
  * Criteria array must have >= 1 entry.
  * evaluate() decision rules:
      deploy     -- every required criterion passes.
      block      -- any required criterion fails.
      needs-human -- required criterion straddles threshold (uncertainty).
      needs-human -- required criterion has no matching result (missing).
  * Uncertainty-aware: [measured - uncertainty, measured + uncertainty] straddles
    threshold -> "uncertain" -> never deploy.
  * Non-required criteria do not affect the top-level decision.
  * EvalDecision is advisory only; it never grants authority.
  * Conformance manifest -- every fixture must match its declared expected result.
"""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.evaluation_contract import (
    EvalDecision,
    evaluate,
    validate_evaluation_contract,
)

CONF = (
    Path(__file__).resolve().parents[1] / "conformance" / "evaluation-contract" / "v0.1"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_contract(**overrides: object) -> dict:
    base: dict = {
        "eval_version": "0.1",
        "contract_id": "ec-test",
        "objective": "Verify accuracy threshold.",
        "criteria": [
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            }
        ],
    }
    base.update(overrides)
    return base


def _result(name: str, measured: float, uncertainty: float = 0.0) -> dict:
    return {"name": name, "measured": measured, "uncertainty": uncertainty}


# ---------------------------------------------------------------------------
# Structural validation -- happy path
# ---------------------------------------------------------------------------


def test_minimal_valid_contract_passes():
    issues = validate_evaluation_contract(_minimal_contract())
    assert issues == []


def test_valid_fixture_from_disk_passes():
    data = json.loads(
        (CONF / "valid" / "all-required-pass.contract.json").read_text(encoding="utf-8")
    )
    assert validate_evaluation_contract(data) == []


# ---------------------------------------------------------------------------
# Forbidden-field guard
# ---------------------------------------------------------------------------


def test_forbidden_field_rejected_at_root():
    data = _minimal_contract()
    data["prefire"] = {"state": "embedded"}
    issues = validate_evaluation_contract(data)
    assert any("forbidden" in i.message for i in issues)


def test_every_prefire_key_is_forbidden_at_root():
    from proof_surface.evaluation_contract import FORBIDDEN_FIELDS

    for key in FORBIDDEN_FIELDS:
        data = _minimal_contract()
        data[key] = "x"
        issues = validate_evaluation_contract(data)
        assert any(i.path == f"$.{key}" and "forbidden" in i.message for i in issues), (
            f"key {key!r} not blocked at root"
        )


def test_forbidden_field_rejected_when_nested_in_criterion():
    data = _minimal_contract()
    data["criteria"][0]["federal_appointment"] = {"role": "eval-authority"}
    issues = validate_evaluation_contract(data)
    assert any(
        "federal_appointment" in i.path and "forbidden" in i.message for i in issues
    )


def test_forbidden_field_rejected_nested_sovereignty_capsule():
    data = _minimal_contract()
    data["criteria"][0]["sovereignty_capsule"] = True
    issues = validate_evaluation_contract(data)
    assert any("forbidden" in i.message for i in issues)


# ---------------------------------------------------------------------------
# additionalProperties:false enforcement
# ---------------------------------------------------------------------------


def test_unknown_root_field_rejected():
    data = _minimal_contract()
    data["approved_by"] = "auto-approver"
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.approved_by" for i in issues)


def test_unknown_criterion_field_rejected():
    data = _minimal_contract()
    data["criteria"][0]["weight"] = 0.5
    issues = validate_evaluation_contract(data)
    assert any("weight" in i.path for i in issues)


# ---------------------------------------------------------------------------
# Schema constraints
# ---------------------------------------------------------------------------


def test_empty_criteria_rejected():
    data = _minimal_contract()
    data["criteria"] = []
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.criteria" for i in issues)


def test_bad_direction_enum_rejected():
    data = _minimal_contract()
    data["criteria"][0]["direction"] = ">"
    issues = validate_evaluation_contract(data)
    assert any("direction" in i.path for i in issues)


def test_missing_contract_id_rejected():
    data = _minimal_contract()
    del data["contract_id"]
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.contract_id" for i in issues)


def test_empty_objective_rejected():
    data = _minimal_contract()
    data["objective"] = "   "
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.objective" for i in issues)


def test_threshold_must_be_number():
    data = _minimal_contract()
    data["criteria"][0]["threshold"] = "ninety"
    issues = validate_evaluation_contract(data)
    assert any("threshold" in i.path for i in issues)


def test_threshold_bool_rejected():
    data = _minimal_contract()
    data["criteria"][0]["threshold"] = True
    issues = validate_evaluation_contract(data)
    assert any("threshold" in i.path for i in issues)


def test_required_must_be_bool():
    data = _minimal_contract()
    data["criteria"][0]["required"] = 1
    issues = validate_evaluation_contract(data)
    assert any("required" in i.path for i in issues)


def test_eval_version_const():
    data = _minimal_contract()
    data["eval_version"] = "2.0"
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.eval_version" for i in issues)


def test_notes_must_be_string_when_present():
    data = _minimal_contract()
    data["notes"] = 42
    issues = validate_evaluation_contract(data)
    assert any(i.path == "$.notes" for i in issues)


# ---------------------------------------------------------------------------
# evaluate() -- deploy when all required pass
# ---------------------------------------------------------------------------


def test_evaluate_deploy_when_all_required_pass():
    contract = _minimal_contract()
    results = [_result("accuracy", 95.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["accuracy"] == "pass"


def test_evaluate_deploy_gte_exact_threshold():
    contract = _minimal_contract()
    results = [_result("accuracy", 90.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["accuracy"] == "pass"


def test_evaluate_deploy_lte_direction():
    contract = _minimal_contract(
        criteria=[
            {
                "name": "latency",
                "metric": "p99_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            }
        ]
    )
    results = [_result("latency", 480.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["latency"] == "pass"


def test_evaluate_non_required_fail_does_not_block():
    contract = _minimal_contract(
        criteria=[
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            },
            {
                "name": "coverage",
                "metric": "line_coverage_pct",
                "threshold": 80.0,
                "direction": ">=",
                "required": False,
            },
        ]
    )
    results = [
        _result("accuracy", 95.0),
        _result("coverage", 70.0),  # fails but not required
    ]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["coverage"] == "fail"


# ---------------------------------------------------------------------------
# evaluate() -- block on required fail
# ---------------------------------------------------------------------------


def test_evaluate_block_when_required_fails_gte():
    contract = _minimal_contract()
    results = [_result("accuracy", 85.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "block"
    assert decision.per_criterion["accuracy"] == "fail"
    assert any("accuracy" in r for r in decision.reasons)


def test_evaluate_block_when_required_fails_lte():
    contract = _minimal_contract(
        criteria=[
            {
                "name": "latency",
                "metric": "p99_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            }
        ]
    )
    results = [_result("latency", 600.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "block"
    assert decision.per_criterion["latency"] == "fail"


def test_evaluate_block_takes_precedence_over_uncertain():
    """If one required criterion fails and another is uncertain, result is block."""
    contract = _minimal_contract(
        criteria=[
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            },
            {
                "name": "latency",
                "metric": "p99_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            },
        ]
    )
    results = [
        _result("accuracy", 80.0),  # fail (no uncertainty)
        _result("latency", 490.0, 20.0),  # uncertain: [470, 510] straddles 500
    ]
    decision = evaluate(contract, results)
    assert decision.decision == "block"


# ---------------------------------------------------------------------------
# evaluate() -- needs-human on uncertainty (straddle)
# ---------------------------------------------------------------------------


def test_evaluate_needs_human_when_straddles_gte():
    """measured=89, uncertainty=2 -> interval [87, 91] straddles threshold=90."""
    contract = _minimal_contract()
    results = [_result("accuracy", 89.0, 2.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "needs-human"
    assert decision.per_criterion["accuracy"] == "uncertain"
    assert any("accuracy" in r for r in decision.reasons)


def test_evaluate_needs_human_when_straddles_lte():
    """measured=495, uncertainty=10 -> interval [485, 505] straddles threshold=500."""
    contract = _minimal_contract(
        criteria=[
            {
                "name": "latency",
                "metric": "p99_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            }
        ]
    )
    results = [_result("latency", 495.0, 10.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "needs-human"
    assert decision.per_criterion["latency"] == "uncertain"


def test_evaluate_zero_uncertainty_no_straddle_pass():
    """No uncertainty: measured exactly at threshold with '>=' is a pass."""
    contract = _minimal_contract()
    results = [_result("accuracy", 90.0, 0.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["accuracy"] == "pass"


def test_evaluate_zero_uncertainty_just_below_fails():
    """No uncertainty: measured just below threshold fails immediately."""
    contract = _minimal_contract()
    results = [_result("accuracy", 89.99, 0.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "block"
    assert decision.per_criterion["accuracy"] == "fail"


# ---------------------------------------------------------------------------
# evaluate() -- needs-human on missing result
# ---------------------------------------------------------------------------


def test_evaluate_needs_human_when_required_result_missing():
    contract = _minimal_contract()
    results = []  # no result for "accuracy"
    decision = evaluate(contract, results)
    assert decision.decision == "needs-human"
    assert decision.per_criterion["accuracy"] == "missing"
    assert any("accuracy" in r for r in decision.reasons)


def test_evaluate_needs_human_when_one_of_two_required_is_missing():
    contract = _minimal_contract(
        criteria=[
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            },
            {
                "name": "latency",
                "metric": "p99_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            },
        ]
    )
    results = [_result("accuracy", 95.0)]  # latency result absent
    decision = evaluate(contract, results)
    assert decision.decision == "needs-human"
    assert decision.per_criterion["latency"] == "missing"


def test_evaluate_missing_non_required_does_not_escalate():
    """A missing non-required criterion leaves a required passing criterion as deploy."""
    contract = _minimal_contract(
        criteria=[
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            },
            {
                "name": "coverage",
                "metric": "line_coverage_pct",
                "threshold": 80.0,
                "direction": ">=",
                "required": False,
            },
        ]
    )
    results = [_result("accuracy", 95.0)]
    decision = evaluate(contract, results)
    assert decision.decision == "deploy"
    assert decision.per_criterion["coverage"] == "missing"


# ---------------------------------------------------------------------------
# evaluate() -- EvalDecision shape
# ---------------------------------------------------------------------------


def test_eval_decision_is_frozen_dataclass():
    contract = _minimal_contract()
    decision = evaluate(contract, [_result("accuracy", 95.0)])
    assert isinstance(decision, EvalDecision)
    assert decision.decision in {"deploy", "block", "needs-human"}
    assert isinstance(decision.reasons, list)
    assert isinstance(decision.per_criterion, dict)


# ---------------------------------------------------------------------------
# Conformance manifest
# ---------------------------------------------------------------------------


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_evaluation_contract(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid but got no issues"


# ---------------------------------------------------------------------------
# Hardening regressions (bulletproofing audit) -- evaluate() validates first
# ---------------------------------------------------------------------------


def test_evaluate_blocks_invalid_contract_not_deploy():
    # An empty contract must NOT yield deploy via the zero-criteria fall-through.
    decision = evaluate({}, [])
    assert decision.decision == "block"


def test_evaluate_blocks_empty_criteria():
    contract = _minimal_contract(criteria=[])
    decision = evaluate(contract, [])
    assert decision.decision == "block"


def test_evaluate_blocks_unknown_direction():
    # A tampered direction must be rejected (validate-first), never silently
    # treated as "<=".
    contract = _minimal_contract(
        criteria=[
            {
                "name": "x",
                "metric": "m",
                "threshold": 1.0,
                "direction": "SKIP",
                "required": True,
            }
        ]
    )
    decision = evaluate(contract, [_result("x", 5.0)])
    assert decision.decision == "block"


def test_compare_unknown_direction_fails_closed():
    from proof_surface.evaluation_contract import _compare

    assert _compare(5.0, 0.0, 1.0, "SKIP") == "fail"


def test_evaluate_valid_contract_still_deploys():
    contract = _minimal_contract()
    decision = evaluate(contract, [_result("accuracy", 95.0)])
    assert decision.decision == "deploy"
