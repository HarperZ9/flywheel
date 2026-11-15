from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from proof_surface import evaluate_gate, validate_gate_request
from proof_surface import pre_execution_gate as peg

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "gate-request.schema.json"


def _now_str(offset_seconds: int = 0) -> str:
    dt = datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt(action: str = "submit_research") -> dict:
    return {
        "authorization_version": "0.1",
        "receipt_id": "ar-human-gap-test",
        "kind": "authorization-grant",
        "principal": {"id": "user:alice@example.com"},
        "agent": {"id": "agent:test"},
        "intent": "Human gap test fixture.",
        "scope": {"allowed_actions": [action], "allowed_targets": []},
        "granted_at": _now_str(-60),
        "expires_at": _now_str(3600),
        "revoked": False,
    }


def _request() -> dict:
    return {
        "planned_action": {
            "action_kind": "submit_research",
            "target": "submission/membrane-submission.md",
        },
        "authorization": _receipt(),
        "budget": {},
    }


def test_human_gap_is_optional_and_not_applicable_when_absent() -> None:
    decision = evaluate_gate(_request())

    assert decision.decision == peg.ALLOW
    assert decision.checks["human_gap"] == peg.NOT_APPLICABLE


def test_required_human_gap_without_evidence_needs_human() -> None:
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
    }

    decision = evaluate_gate(request)

    assert decision.decision == peg.NEEDS_HUMAN
    assert decision.checks["human_gap"] == peg.UNKNOWN
    assert any("human gap open" in reason for reason in decision.reasons)


def test_required_human_gap_without_operator_attestation_needs_human() -> None:
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
        "evidence_label": "CONTRIBUTION-LEDGER row M1",
        "evidence_digest": "a" * 64,
        "operator_attested": False,
    }

    decision = evaluate_gate(request)

    assert decision.decision == peg.NEEDS_HUMAN
    assert decision.checks["human_gap"] == peg.UNKNOWN
    assert any("operator attestation" in reason for reason in decision.reasons)


def test_external_human_attestation_allows_when_other_checks_pass() -> None:
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
        "evidence_label": "CONTRIBUTION-LEDGER row M1",
        "evidence_digest": "a" * 64,
        "operator_attested": True,
    }

    decision = evaluate_gate(request)

    assert decision.decision == peg.ALLOW
    assert decision.checks["human_gap"] == peg.PASS


def test_human_gap_shape_is_strict() -> None:
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
        "evidence_digest": "not-hex",
        "claimed_by_model": True,
    }

    issues = validate_gate_request(request)

    assert any(issue.path == "$.human_gap.evidence_digest" for issue in issues)
    assert any(issue.path == "$.human_gap.claimed_by_model" for issue in issues)


def test_forbidden_fields_are_rejected_inside_human_gap() -> None:
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
        "guardrail_posture": "trusted",
    }

    issues = validate_gate_request(request)

    assert any(
        "guardrail_posture" in issue.path and "forbidden" in issue.message
        for issue in issues
    )


def test_json_schema_accepts_human_gap_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    request = _request()
    request["human_gap"] = {
        "requires_human_act": True,
        "act_kind": "authorship_attestation",
        "evidence_label": "CONTRIBUTION-LEDGER row M1",
        "evidence_digest": "a" * 64,
        "operator_attested": True,
    }

    assert list(validator.iter_errors(request)) == []
