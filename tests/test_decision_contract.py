import json

import pytest

from harness import decision_contract as contract
from harness.decision_contract import (
    DecisionContractError,
    evaluate_proposal,
    validate_request,
)
from harness.evidence_json import canonical_sha256


def _request(**overrides):
    payload = {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": "decision_1",
        "state": "Choose the safest route.",
        "choices": [
            {"id": "local", "description": "Use the local model."},
            {"id": "hosted", "description": "Use a hosted endpoint."},
        ],
        "eligible_choice_ids": ["local", "hosted"],
        "evidence_refs": ["ev_roster", "ev_stats"],
    }
    payload.update(overrides)
    return payload


def _proposal(choice_id="local", refs=None, **extra):
    body = {
        "choice_id": choice_id,
        "evidence_refs": ["ev_roster"] if refs is None else refs,
    }
    body.update(extra)
    return json.dumps(body)


def test_validate_request_returns_independent_snapshot():
    payload = _request()
    snapshot = validate_request(payload)
    payload["choices"][0]["description"] = "mutated"
    payload["eligible_choice_ids"].append("new")

    assert snapshot == _request()
    assert snapshot is not payload
    assert snapshot["choices"][0] is not payload["choices"][0]


@pytest.mark.parametrize(
    "payload",
    [
        _request(extra="nope"),
        _request(schema="wrong"),
        _request(decision_ref=""),
        _request(state="x" * 8193),
        _request(choices=[]),
        _request(choices=[{"id": "same", "description": "a"}, {"id": "same", "description": "b"}]),
        _request(eligible_choice_ids=["missing"]),
        _request(evidence_refs=["ev_roster", "ev_roster"]),
        _request(choices=[{"id": "rm -rf /", "description": "bad"}]),
    ],
)
def test_validate_request_rejects_bad_shape(payload):
    with pytest.raises(DecisionContractError):
        validate_request(payload)


def test_validate_request_rejects_nonfinite_values():
    payload = _request()
    payload["state"] = float("nan")

    with pytest.raises(DecisionContractError):
        validate_request(payload)


def test_evaluate_proposal_selects_declared_eligible_choice():
    req = validate_request(_request())
    result = evaluate_proposal(req, _proposal("hosted", ["ev_stats"]), scorer_ref="stub_scorer")

    assert result == {
        "schema": "flywheel.decision-result/v1",
        "disposition": "selected",
        "choice_id": "hosted",
        "reason_code": "selected",
        "evidence_refs": ["ev_stats"],
        "request_sha256": canonical_sha256(req),
        "response_sha256": result["response_sha256"],
        "scorer_ref": "stub_scorer",
        "does_not_prove": result["does_not_prove"],
    }
    assert len(result["response_sha256"]) == 64
    assert "semantic correctness" in result["does_not_prove"]


def test_evaluate_proposal_accepts_explicit_abstain():
    req = validate_request(_request())
    result = evaluate_proposal(req, _proposal(None, []), scorer_ref="stub_scorer")

    assert result["disposition"] == "abstained"
    assert result["choice_id"] is None
    assert result["reason_code"] == "abstain"
    assert result["evidence_refs"] == []


def test_empty_eligibility_abstains_without_parsing_response():
    req = validate_request(_request(eligible_choice_ids=[]))
    result = evaluate_proposal(req, '{"choice_id": "local"', scorer_ref="stub_scorer")

    assert result["disposition"] == "abstained"
    assert result["choice_id"] is None
    assert result["reason_code"] == "empty_eligibility"


@pytest.mark.parametrize(
    "response, reason",
    [
        ("not json", "malformed_json"),
        ('{"choice_id": "local", "choice_id": "hosted", "evidence_refs": []}', "duplicate_key"),
        ('{"choice_id": NaN, "evidence_refs": []}', "malformed_json"),
        (json.dumps({"choice_id": "local", "evidence_refs": [], "confidence": 0.9}), "invalid_shape"),
        (json.dumps({"choice_id": "missing", "evidence_refs": []}), "unknown_choice"),
        (json.dumps({"choice_id": "hosted", "evidence_refs": []}), "ineligible_choice"),
        (json.dumps({"choice_id": None, "evidence_refs": ["invented"]}), "invented_evidence_ref"),
        ('{"choice_id": null, "evidence_refs": [{}]}', "invalid_shape"),
        ("\ud800", "malformed_json"),
        ("x" * 4097, "response_oversize"),
    ],
)
def test_malformed_or_unsafe_proposals_abstain_without_echo(response, reason):
    req = validate_request(_request(eligible_choice_ids=["local"]))
    result = evaluate_proposal(req, response, scorer_ref="stub_scorer")

    assert result["disposition"] == "abstained"
    assert result["choice_id"] is None
    assert result["reason_code"] == reason
    assert result["evidence_refs"] == []
    assert response not in json.dumps(result)


def test_oversize_response_preflight_precedes_invalid_scorer_hashing(monkeypatch):
    req = validate_request(_request())
    monkeypatch.setattr(
        contract, "_response_sha256",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("response hashed")))

    result = evaluate_proposal(
        req, "x" * (contract.MAX_RESPONSE_BYTES + 1), scorer_ref="bad ref")

    assert result["reason_code"] == "response_oversize"
    assert result["response_sha256"] is None


def test_oversize_response_preflight_precedes_empty_eligibility_hashing(monkeypatch):
    req = validate_request(_request(eligible_choice_ids=[]))
    monkeypatch.setattr(
        contract, "_response_sha256",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("response hashed")))

    result = evaluate_proposal(
        req, "x" * (contract.MAX_RESPONSE_BYTES + 1), scorer_ref="stub_scorer")

    assert result["reason_code"] == "response_oversize"
    assert result["response_sha256"] is None


def test_response_preflight_applies_exact_utf8_byte_bound_before_hashing(monkeypatch):
    req = validate_request(_request(eligible_choice_ids=["local"]))
    monkeypatch.setattr(
        contract, "_response_sha256",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("response hashed")))

    result = evaluate_proposal(
        req, "é" * contract.MAX_RESPONSE_BYTES, scorer_ref="stub_scorer")

    assert result["reason_code"] == "response_oversize"
    assert result["response_sha256"] is None


def test_invalid_scorer_ref_abstains():
    req = validate_request(_request())
    result = evaluate_proposal(req, _proposal("local"), scorer_ref="bad ref")

    assert result["reason_code"] == "invalid_scorer_ref"
    assert result["disposition"] == "abstained"


@pytest.mark.parametrize("scorer", [1, ["invalid"], {"invalid": True}])
@pytest.mark.parametrize("response", [None, "x" * 4097], ids=["nonstring", "oversize"])
def test_response_preflight_sanitizes_nonstr_scorer(scorer, response):
    result = evaluate_proposal(_request(), response, scorer_ref=scorer)
    assert result["disposition"] == "abstained"
    assert result["scorer_ref"] == ""
    assert result["response_sha256"] is None


def test_deep_json_abstains_without_recursion_failure():
    response = ('{"choice_id":' + '[' * 700 + 'null' + ']' * 700
                + ',"evidence_refs":[]}')
    result = evaluate_proposal(_request(), response, scorer_ref="control")
    assert result["disposition"] == "abstained"
    assert result["reason_code"] == "malformed_json"
