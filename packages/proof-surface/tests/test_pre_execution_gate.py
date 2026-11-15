"""Tests for the pre-execution gate contract.

Mirrors the style of test_authorization_receipt.py exactly.  Every assertion is
meaningful; no "it didn't crash" tests.

Contract invariants exercised here:
  * Default-deny: allow ONLY when every applicable check positively passes.
  * Fail-closed-on-unknown: any unknown dimension yields needs-human, never allow.
  * Authorization check: invalid receipt or out-of-scope action -> deny.
  * Budget check: breach -> deny; estimated cost without remaining -> needs-human.
  * State check: DRIFT -> deny; UNVERIFIABLE -> needs-human; digest mismatch -> deny.
  * Forbidden-field guard: recursive, fail-closed, same set as authorization-receipt.
  * additionalProperties:false at root and every nested object.
  * Advisory-not-authority: GateDecision is a recommendation; never an authority grant.
  * Conformance manifest: every fixture must match its declared expected result.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proof_surface import GateDecision, evaluate_gate, validate_gate_request
from proof_surface import pre_execution_gate as peg

CONF = (
    Path(__file__).resolve().parents[1] / "conformance" / "pre-execution-gate" / "v0.1"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now_str(offset_seconds: int = 0) -> str:
    dt = datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_receipt(
    *,
    actions: list[str] | None = None,
    targets: list[str] | None = None,
    revoked: bool = False,
    granted_offset: int = -3600,
    expires_offset: int = 3600,
) -> dict:
    """Build a minimal structurally and temporally valid authorization receipt."""
    return {
        "authorization_version": "0.1",
        "receipt_id": "ar-gate-test-fixture",
        "kind": "authorization-grant",
        "principal": {"id": "user:alice@example.com"},
        "agent": {"id": "agent:test"},
        "intent": "Gate test fixture.",
        "scope": {
            "allowed_actions": actions if actions is not None else ["read_file"],
            "allowed_targets": targets if targets is not None else [],
        },
        "granted_at": _now_str(granted_offset),
        "expires_at": _now_str(expires_offset),
        "revoked": revoked,
    }


def _valid_request(
    *,
    action_kind: str = "read_file",
    target: str = "some/path.txt",
    estimated_cost: dict | None = None,
    receipt: dict | None = None,
    budget: dict | None = None,
    state: dict | None = None,
    include_state: bool = False,
) -> dict:
    """Build a valid gate request for decision tests."""
    req: dict = {
        "planned_action": {
            "action_kind": action_kind,
            "target": target,
        },
        "authorization": receipt
        if receipt is not None
        else _valid_receipt(actions=[action_kind], targets=[]),
        "budget": budget if budget is not None else {},
    }
    if estimated_cost is not None:
        req["planned_action"]["estimated_cost"] = estimated_cost
    if state is not None or include_state:
        if state is not None:
            req["state"] = state
    return req


def _load_shape_fixture(relative_path: str) -> dict:
    return json.loads((CONF / relative_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Shape validation -- happy path
# ---------------------------------------------------------------------------


def test_minimal_valid_request_shape_passes():
    data = _load_shape_fixture("valid/minimal.request.json")
    assert validate_gate_request(data) == []


# ---------------------------------------------------------------------------
# Forbidden-field guard (recursive, fail-closed)
# ---------------------------------------------------------------------------


def test_forbidden_field_at_root_rejected():
    req = _valid_request()
    req["federal_appointment"] = {"state": "embedded"}
    issues = validate_gate_request(req)
    assert any("forbidden" in i.message for i in issues)


def test_every_prefire_key_is_forbidden_at_root():
    for key in peg.FORBIDDEN_FIELDS:
        req = _valid_request()
        req[key] = "x"
        issues = validate_gate_request(req)
        assert any(i.path == f"$.{key}" and "forbidden" in i.message for i in issues), (
            f"key {key!r} not blocked at root"
        )


def test_forbidden_field_nested_in_authorization_rejected():
    req = _valid_request()
    req["authorization"]["scope"]["authorization_context_mode"] = (
        "consume_verified_native_state"
    )
    issues = validate_gate_request(req)
    assert any(
        i.path.endswith("authorization_context_mode") and "forbidden" in i.message
        for i in issues
    )


def test_forbidden_field_nested_in_planned_action_rejected():
    req = _valid_request()
    req["planned_action"]["prefire"] = True
    issues = validate_gate_request(req)
    assert any(i.path.endswith("prefire") and "forbidden" in i.message for i in issues)


def test_forbidden_field_nested_in_budget_rejected():
    req = _valid_request()
    req["budget"]["run_state"] = "active"
    issues = validate_gate_request(req)
    assert any(
        i.path.endswith("run_state") and "forbidden" in i.message for i in issues
    )


def test_forbidden_field_nested_in_state_rejected():
    req = _valid_request()
    req["state"] = {"witness_verdict": "MATCH", "self_applicable": True}
    issues = validate_gate_request(req)
    assert any(
        i.path.endswith("self_applicable") and "forbidden" in i.message for i in issues
    )


# ---------------------------------------------------------------------------
# additionalProperties:false enforcement
# ---------------------------------------------------------------------------


def test_unknown_root_field_rejected():
    req = _valid_request()
    req["extra_authority"] = "full_access"
    issues = validate_gate_request(req)
    assert any(i.path == "$.extra_authority" for i in issues)


def test_unknown_planned_action_field_rejected():
    req = _valid_request()
    req["planned_action"]["clearance"] = "top_secret"
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.clearance" for i in issues)


def test_unknown_estimated_cost_field_rejected():
    req = _valid_request(estimated_cost={"tokens": 100, "gpu_ms": 50})
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.estimated_cost.gpu_ms" for i in issues)


def test_unknown_budget_field_rejected():
    req = _valid_request(budget={"remaining_tokens": 1000, "extra_budget": 999})
    issues = validate_gate_request(req)
    assert any(i.path == "$.budget.extra_budget" for i in issues)


def test_unknown_state_field_rejected():
    req = _valid_request()
    req["state"] = {"witness_verdict": "MATCH", "trust_level": "high"}
    issues = validate_gate_request(req)
    assert any(i.path == "$.state.trust_level" for i in issues)


# ---------------------------------------------------------------------------
# Required-field shape checks
# ---------------------------------------------------------------------------


def test_missing_planned_action_rejected():
    req = _valid_request()
    del req["planned_action"]
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action" for i in issues)


def test_missing_action_kind_rejected():
    req = _valid_request()
    del req["planned_action"]["action_kind"]
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.action_kind" for i in issues)


def test_missing_target_rejected():
    req = _valid_request()
    del req["planned_action"]["target"]
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.target" for i in issues)


def test_empty_action_kind_rejected():
    req = _valid_request()
    req["planned_action"]["action_kind"] = "  "
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.action_kind" for i in issues)


def test_authorization_must_be_object():
    req = _valid_request()
    req["authorization"] = "not-an-object"
    issues = validate_gate_request(req)
    assert any(i.path == "$.authorization" for i in issues)


def test_budget_must_be_object():
    req = _valid_request()
    req["budget"] = "lots"
    issues = validate_gate_request(req)
    assert any(i.path == "$.budget" for i in issues)


def test_negative_remaining_tokens_rejected():
    req = _valid_request(budget={"remaining_tokens": -1})
    issues = validate_gate_request(req)
    assert any(i.path == "$.budget.remaining_tokens" for i in issues)


def test_negative_estimated_cost_rejected():
    req = _valid_request(estimated_cost={"tokens": -50})
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.estimated_cost.tokens" for i in issues)


def test_bool_estimated_cost_rejected():
    req = _valid_request(estimated_cost={"wall_ms": True})
    issues = validate_gate_request(req)
    assert any(i.path == "$.planned_action.estimated_cost.wall_ms" for i in issues)


def test_invalid_witness_verdict_rejected():
    req = _valid_request()
    req["state"] = {"witness_verdict": "TRUSTED"}
    issues = validate_gate_request(req)
    assert any(i.path == "$.state.witness_verdict" for i in issues)


def test_bad_digest_format_rejected():
    req = _valid_request()
    req["state"] = {
        "witness_verdict": "MATCH",
        "target_digest": "not-hex",
        "expected_digest": "a" * 64,
    }
    issues = validate_gate_request(req)
    assert any(i.path == "$.state.target_digest" for i in issues)


def test_state_is_optional():
    req = _valid_request()
    assert "state" not in req
    issues = validate_gate_request(req)
    assert issues == []


# ---------------------------------------------------------------------------
# evaluate_gate -- allow path (all checks pass)
# ---------------------------------------------------------------------------


def test_allow_when_all_checks_pass():
    req = _valid_request()
    decision = evaluate_gate(req)
    assert decision.decision == peg.ALLOW
    assert decision.checks["authorization"] == peg.PASS
    assert decision.checks["budget"] == peg.NOT_APPLICABLE
    assert decision.checks["state"] == peg.NOT_APPLICABLE


def test_allow_with_budget_within_limits():
    req = _valid_request(
        estimated_cost={"tokens": 100, "wall_ms": 500},
        budget={"remaining_tokens": 1000, "remaining_wall_ms": 5000},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.ALLOW
    assert decision.checks["authorization"] == peg.PASS
    assert decision.checks["budget"] == peg.PASS
    assert decision.checks["state"] == peg.NOT_APPLICABLE


def test_allow_with_state_match():
    req = _valid_request(
        state={"witness_verdict": "MATCH"},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.ALLOW
    assert decision.checks["state"] == peg.PASS


def test_allow_with_matching_digests():
    digest = "a" * 64
    req = _valid_request(
        state={
            "witness_verdict": "MATCH",
            "target_digest": digest,
            "expected_digest": digest,
        }
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.ALLOW
    assert decision.checks["state"] == peg.PASS


# ---------------------------------------------------------------------------
# evaluate_gate -- deny: authorization failures
# ---------------------------------------------------------------------------


def test_deny_on_out_of_scope_action():
    req = _valid_request(
        action_kind="write_file",
        receipt=_valid_receipt(actions=["read_file"]),
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL
    assert any("authorization denied" in r for r in decision.reasons)


def test_deny_on_revoked_receipt():
    req = _valid_request(receipt=_valid_receipt(revoked=True))
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL
    assert any("revoked" in r for r in decision.reasons)


def test_deny_on_expired_receipt():
    req = _valid_request(
        receipt=_valid_receipt(granted_offset=-7200, expires_offset=-3600)
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL
    assert any("expired" in r for r in decision.reasons)


def test_deny_on_invalid_authorization_receipt():
    req = _valid_request()
    req["authorization"] = {"authorization_version": "0.1"}  # structurally broken
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL
    assert any("invalid authorization" in r for r in decision.reasons)


def test_deny_on_target_not_in_allowed_targets():
    req = _valid_request(
        target="C:/dev/secret/",
        receipt=_valid_receipt(
            actions=["read_file"],
            targets=["C:/dev/public/"],
        ),
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL


def test_deny_on_empty_allowed_actions():
    req = _valid_request(receipt=_valid_receipt(actions=[]))
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL


# ---------------------------------------------------------------------------
# evaluate_gate -- deny: budget failures
# ---------------------------------------------------------------------------


def test_deny_on_token_budget_breach():
    req = _valid_request(
        estimated_cost={"tokens": 5000},
        budget={"remaining_tokens": 1000},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["budget"] == peg.FAIL
    assert any("tokens" in r for r in decision.reasons)


def test_deny_on_wall_ms_budget_breach():
    req = _valid_request(
        estimated_cost={"wall_ms": 10000},
        budget={"remaining_wall_ms": 5000},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["budget"] == peg.FAIL
    assert any("wall_ms" in r for r in decision.reasons)


def test_deny_on_remaining_actions_zero():
    req = _valid_request(
        estimated_cost={"tokens": 100},
        budget={"remaining_tokens": 1000, "remaining_actions": 0},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["budget"] == peg.FAIL
    assert any("remaining_actions" in r for r in decision.reasons)


def test_deny_on_remaining_actions_negative():
    req = _valid_request(budget={"remaining_actions": -1})
    # This is a shape violation, so the gate denies on structural grounds.
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY


def test_deny_on_remaining_actions_zero_no_estimated_cost():
    # remaining_actions <= 0 blocks even without an estimated_cost.
    req = _valid_request(budget={"remaining_actions": 0})
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["budget"] == peg.FAIL


# ---------------------------------------------------------------------------
# evaluate_gate -- needs-human: unknown budget
# ---------------------------------------------------------------------------


def test_needs_human_on_estimated_cost_with_no_remaining_tokens():
    """Estimated tokens given, remaining_tokens absent -> unknown -> needs-human."""
    req = _valid_request(
        estimated_cost={"tokens": 500},
        budget={},  # remaining_tokens absent
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.NEEDS_HUMAN
    assert decision.checks["budget"] == peg.UNKNOWN
    assert any("unknown" in r for r in decision.reasons)


def test_needs_human_on_estimated_wall_ms_with_no_remaining():
    req = _valid_request(
        estimated_cost={"wall_ms": 2000},
        budget={},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.NEEDS_HUMAN
    assert decision.checks["budget"] == peg.UNKNOWN


def test_no_estimated_cost_budget_is_not_applicable():
    req = _valid_request(budget={"remaining_tokens": 1000})
    decision = evaluate_gate(req)
    assert decision.checks["budget"] == peg.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# evaluate_gate -- deny: state failures
# ---------------------------------------------------------------------------


def test_deny_on_witness_verdict_drift():
    req = _valid_request(state={"witness_verdict": "DRIFT"})
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["state"] == peg.FAIL
    assert any("DRIFT" in r for r in decision.reasons)


def test_deny_on_digest_mismatch():
    req = _valid_request(
        state={
            "target_digest": "a" * 64,
            "expected_digest": "b" * 64,
        }
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["state"] == peg.FAIL
    assert any("digest" in r for r in decision.reasons)


def test_deny_on_drift_plus_digest_mismatch():
    """Both DRIFT and digest mismatch -> still deny (fail wins)."""
    req = _valid_request(
        state={
            "witness_verdict": "DRIFT",
            "target_digest": "a" * 64,
            "expected_digest": "b" * 64,
        }
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["state"] == peg.FAIL


# ---------------------------------------------------------------------------
# evaluate_gate -- needs-human: state unknown
# ---------------------------------------------------------------------------


def test_needs_human_on_witness_verdict_unverifiable():
    req = _valid_request(state={"witness_verdict": "UNVERIFIABLE"})
    decision = evaluate_gate(req)
    assert decision.decision == peg.NEEDS_HUMAN
    assert decision.checks["state"] == peg.UNKNOWN
    assert any("UNVERIFIABLE" in r for r in decision.reasons)


def test_state_absent_is_not_applicable():
    req = _valid_request()
    decision = evaluate_gate(req)
    assert decision.checks["state"] == peg.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# evaluate_gate -- fail-closed precedence: deny beats needs-human
# ---------------------------------------------------------------------------


def test_deny_beats_unknown_when_auth_fails_and_budget_unknown():
    """Auth fail + budget unknown -> deny (fail takes priority over unknown)."""
    req = _valid_request(
        action_kind="write_file",
        receipt=_valid_receipt(actions=["read_file"]),
        estimated_cost={"tokens": 100},
        budget={},  # unknown budget
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL
    assert decision.checks["budget"] == peg.UNKNOWN


def test_deny_beats_unknown_when_state_drifts_and_budget_unknown():
    req = _valid_request(
        estimated_cost={"tokens": 100},
        budget={},
        state={"witness_verdict": "DRIFT"},
    )
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY


# ---------------------------------------------------------------------------
# evaluate_gate -- structural invalidity causes deny
# ---------------------------------------------------------------------------


def test_invalid_shape_causes_deny():
    """A structurally invalid request (not even a dict) must deny."""
    decision = evaluate_gate(
        {"planned_action": None, "authorization": {}, "budget": {}}
    )
    assert decision.decision == peg.DENY
    assert decision.checks["authorization"] == peg.FAIL


def test_forbidden_field_in_request_causes_deny():
    req = _valid_request()
    req["federal_appointment"] = "special"
    decision = evaluate_gate(req)
    assert decision.decision == peg.DENY


# ---------------------------------------------------------------------------
# GateDecision is advisory-not-authority
# ---------------------------------------------------------------------------


def test_gate_decision_is_dataclass_not_callable():
    """GateDecision must be a plain data record -- not a callable or executable."""
    req = _valid_request()
    decision = evaluate_gate(req)
    assert isinstance(decision, GateDecision)
    assert hasattr(decision, "decision")
    assert hasattr(decision, "reasons")
    assert hasattr(decision, "checks")
    # It must not be callable as authority.
    assert not callable(decision)


def test_gate_decision_allow_has_no_authority_language():
    """An allow decision must not claim to grant authority -- just reports pass."""
    req = _valid_request()
    decision = evaluate_gate(req)
    assert decision.decision == peg.ALLOW
    combined = " ".join(decision.reasons).lower()
    # The decision says checks passed, not that authority is granted.
    assert "grant" not in combined or "granted" not in combined
    # decision field is simply the string "allow"
    assert decision.decision == "allow"


def test_decision_values_are_the_expected_strings():
    assert peg.ALLOW == "allow"
    assert peg.DENY == "deny"
    assert peg.NEEDS_HUMAN == "needs-human"


# ---------------------------------------------------------------------------
# Conformance manifest
# ---------------------------------------------------------------------------


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_gate_request(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid but got: {issues}"
        else:
            assert issues, (
                f"{fixture['path']} should be invalid but validate_gate_request returned no issues"
            )


# ---------------------------------------------------------------------------
# Hardening regressions (bulletproofing audit)
# ---------------------------------------------------------------------------


def test_half_digest_pair_is_structurally_rejected():
    # Only one of target_digest/expected_digest present must not yield a silent PASS.
    req = _valid_request(state={"target_digest": "a" * 64})
    issues = validate_gate_request(req)
    assert any(i.path == "$.state" for i in issues)
    assert evaluate_gate(req).decision == peg.DENY


def test_check_state_half_digest_is_unknown_not_pass():
    # Directly exercise the check layer (defence in depth): one digest -> UNKNOWN.
    result, _reasons = peg._check_state({"target_digest": "a" * 64})
    assert result == peg.UNKNOWN


def test_confirming_witness_verdicts_are_not_structurally_rejected():
    for verdict in ("MATCH", "COHERENT", "CORROBORATED"):
        req = _valid_request(state={"witness_verdict": verdict})
        assert validate_gate_request(req) == [], verdict
        # confirming verdict + authorized action + no budget concern -> allow
        assert evaluate_gate(req).decision == peg.ALLOW, verdict


def test_view_differs_and_quarantine_verdicts_deny():
    for verdict in ("VIEW_DIFFERS_FROM_SOURCE", "QUARANTINE_READ_PATH_DIVERGENCE"):
        req = _valid_request(state={"witness_verdict": verdict})
        assert validate_gate_request(req) == [], verdict
        assert evaluate_gate(req).decision == peg.DENY, verdict
