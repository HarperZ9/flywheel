from copy import deepcopy
import pytest
from harness.evidence_journey import (
    append_event,
    new_journey,
    project_journey,
    verify_journey,
)
STAGES = ("intake", "decomposed", "preflight", "running", "concluded", "exported")


def _journey():
    return new_journey(
        journey_id="journey-1",
        goal="Explain and repair the failure",
        intake={"summary": "test failed", "receipt_refs": ["receipt:intake"]},
        created_at="2026-08-12T12:00:00Z",
    )
def _event(stage, **fields):
    return {
        "stage": stage,
        "occurred_at": "2026-08-12T12:01:00Z",
        **fields,
    }
def _claim(verdict="UNDECIDED", **fields):
    claim = {
        "claim_id": "claim-root",
        "statement": "The failure is reproducible",
        "depends_on": [],
        "verdict": verdict,
        "receipt_refs": ["receipt:root"],
        **fields,
    }
    if verdict in {"UNDECIDED", "UNVERIFIABLE"}:
        claim.setdefault("reason", "checker has not run")
    return claim
def _advance(journey, target):
    for stage in STAGES[STAGES.index(journey["stage"]) + 1:STAGES.index(target) + 1]:
        journey = append_event(journey, _event(stage))
    return journey
def test_new_journey_has_exact_schema_and_copies_its_intake():
    intake = {"summary": "test failed", "nested": {"attempt": 1}}
    original = deepcopy(intake)
    journey = new_journey(
        journey_id="journey-1", goal="Repair", intake=intake,
        created_at="2026-08-12T12:00:00Z",
    )

    assert journey["schema"] == "flywheel.evidence-journey/v1"
    assert journey["stage"] == "intake"
    assert journey["events"] == []
    assert journey["event_head_sha256"] is None
    intake["nested"]["attempt"] = 2
    assert journey["intake"] == original


@pytest.mark.parametrize("stage", ["intake", "preflight", "INTAKE", "unknown"])
def test_state_machine_rejects_same_skipped_or_unknown_transition(stage):
    with pytest.raises(ValueError, match="transition|stage"):
        append_event(_journey(), _event(stage))


def test_state_machine_accepts_each_stage_in_exact_order():
    journey = _advance(_journey(), "exported")
    assert [event["stage"] for event in journey["events"]] == list(STAGES[1:])
    assert journey["stage"] == "exported"


def test_append_copies_inputs_and_binds_each_event_to_the_prior_hash():
    journey = _journey()
    event = _event("decomposed", claims=[_claim()])
    original_journey, original_event = deepcopy(journey), deepcopy(event)

    decomposed = append_event(journey, event)
    preflight = append_event(decomposed, _event("preflight"))

    assert journey == original_journey
    assert event == original_event
    assert decomposed["events"][0]["prior_event_sha256"] is None
    assert preflight["events"][1]["prior_event_sha256"] == decomposed["event_head_sha256"]
    assert preflight["event_head_sha256"] == preflight["events"][1]["event_sha256"]


def test_verifier_detects_event_content_or_chain_tampering():
    journey = _advance(_journey(), "preflight")
    journey["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    result = verify_journey(journey)
    assert result["verdict"] == "FAIL"
    assert "hash" in result["reason"]


@pytest.mark.parametrize(
    "claims, message",
    [
        ([_claim(depends_on=["missing"])], "missing"),
        ([_claim(depends_on=["claim-root"])], "cycle"),
        ([
            _claim(depends_on=["claim-child"]),
            _claim(claim_id="claim-child", depends_on=["claim-root"]),
        ], "cycle"),
    ],
)
def test_claim_dependency_graph_rejects_missing_nodes_and_cycles_atomically(claims, message):
    journey = _journey()
    with pytest.raises(ValueError, match=message):
        append_event(journey, _event("decomposed", claims=claims))
    assert journey["events"] == []


@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"])
def test_claims_accept_exact_four_way_verdicts(verdict):
    journey = append_event(_journey(), _event("decomposed", claims=[_claim(verdict)]))
    assert project_journey(journey, lens="verify")["verdicts"] == {"claim-root": verdict}


def test_claims_reject_verdicts_outside_the_four_way_vocabulary():
    with pytest.raises(ValueError, match="verdict"):
        append_event(_journey(), _event("decomposed", claims=[_claim("MATCH")]))


def test_undecided_and_unverifiable_claims_require_a_reason():
    claim = _claim("UNDECIDED")
    del claim["reason"]
    with pytest.raises(ValueError, match="reason"):
        append_event(_journey(), _event("decomposed", claims=[claim]))


def test_null_metrics_require_reasons_and_consistent_denominators():
    null_metric = {"metric_id": "latency", "value": None, "denominator": 0}
    with pytest.raises(ValueError, match="reason"):
        append_event(_journey(), _event("decomposed", metrics=[null_metric]))

    inconsistent = {
        "metric_id": "success-rate", "value": 1.5, "numerator": 3,
        "denominator": 2, "denominator_id": "attempts",
    }
    with pytest.raises(ValueError, match="denominator"):
        append_event(_journey(), _event("decomposed", metrics=[inconsistent]))


def test_reused_denominator_id_must_keep_the_same_denominator():
    journey = append_event(_journey(), _event(
        "decomposed", metrics=[{
            "metric_id": "covered", "value": 0.5, "numerator": 1,
            "denominator": 2, "denominator_id": "cases",
        }],
    ))
    with pytest.raises(ValueError, match="denominator"):
        append_event(journey, _event(
            "preflight", metrics=[{
                "metric_id": "covered", "value": 0.5, "numerator": 2,
                "denominator": 4, "denominator_id": "cases",
            }],
        ))


@pytest.mark.parametrize("field", ["metrics", "attestations", "claims", "next_actions"])
def test_event_collections_require_exact_lists(field):
    with pytest.raises(ValueError, match=field):
        append_event(_journey(), _event("decomposed", **{field: {}}))


@pytest.mark.parametrize(
    "metric",
    [
        {"metric_id": "rate", "value": 0.9, "numerator": 1, "denominator": 2},
        {"metric_id": "rate", "value": 1.0, "numerator": 0, "denominator": 0},
    ],
)
def test_metric_value_must_be_consistent_with_its_counts(metric):
    with pytest.raises(ValueError, match="denominator"):
        append_event(_journey(), _event("decomposed", metrics=[metric]))


def _attestation(**fields):
    return {
        "subject": "claim-root",
        "role": "reviewer",
        "scope": ["statement", "evidence"],
        "basis": ["receipt:root"],
        "issued_at": "2026-08-12T11:00:00Z",
        "expires_at": "2026-08-12T13:00:00Z",
        "signature_state": "unsigned",
        **fields,
    }


@pytest.mark.parametrize("field", ["subject", "role", "scope", "basis", "issued_at", "expires_at"])
def test_attestations_require_all_identity_scope_basis_and_time_fields(field):
    attestation = _attestation()
    del attestation[field]
    with pytest.raises(ValueError, match=field):
        append_event(_journey(), _event("decomposed", attestations=[attestation]))


def test_unsigned_attestation_is_explicit_and_cannot_satisfy_signed_requirement():
    attestation = _attestation(requires_signature=True)
    with pytest.raises(ValueError, match="signed"):
        append_event(_journey(), _event("decomposed", attestations=[attestation]))

    missing_state = _attestation()
    del missing_state["signature_state"]
    with pytest.raises(ValueError, match="signature_state"):
        append_event(_journey(), _event("decomposed", attestations=[missing_state]))


def test_attestation_requirement_flags_require_exact_booleans():
    with pytest.raises(ValueError, match="requires_signature"):
        append_event(_journey(), _event(
            "decomposed", attestations=[_attestation(requires_signature="true")],
        ))


def test_expired_attestation_is_rejected_when_active_attestation_is_required():
    attestation = _attestation(
        expires_at="2026-08-12T12:00:30Z", requires_active=True,
    )
    with pytest.raises(ValueError, match="expired"):
        append_event(_journey(), _event("decomposed", attestations=[attestation]))


def test_active_signed_attestation_can_satisfy_both_requirements():
    attestation = _attestation(
        signature_state="signed", signature="ed25519:abc",
        requires_signature=True, requires_active=True,
    )
    journey = append_event(
        _journey(), _event("decomposed", attestations=[attestation]),
    )
    assert verify_journey(journey)["verdict"] == "PASS"


def test_attestation_scope_and_basis_may_be_nonempty_strings():
    attestation = _attestation(scope="claim", basis="receipt:root")
    journey = append_event(
        _journey(), _event("decomposed", attestations=[attestation]),
    )
    assert verify_journey(journey)["verdict"] == "PASS"


def test_advisory_actions_require_basis_and_cannot_carry_verdict_mutations():
    action = {"action_id": "rerun", "description": "Rerun the test", "basis_refs": []}
    with pytest.raises(ValueError, match="basis_refs"):
        append_event(_journey(), _event("decomposed", next_actions=[action]))

    action["basis_refs"] = ["receipt:intake"]
    action["claim_verdict"] = "PASS"
    with pytest.raises(ValueError, match="verdict"):
        append_event(_journey(), _event("decomposed", next_actions=[action]))


def test_rescue_diagnose_and_verify_lenses_expose_identical_evidence_facts():
    journey = append_event(_journey(), _event(
        "decomposed",
        claims=[_claim("FAIL", reason="reproduced")],
        next_actions=[{
            "action_id": "inspect", "description": "Inspect the trace",
            "basis_refs": ["receipt:root"],
        }],
    ))
    projections = [project_journey(journey, lens=lens) for lens in (
        "rescue", "diagnose", "verify",
    )]
    evidence_keys = (
        "journey_id", "event_head_sha256", "claim_ids", "verdicts", "receipt_refs",
    )
    assert [{key: view[key] for key in evidence_keys} for view in projections] == [
        {key: projections[0][key] for key in evidence_keys},
    ] * 3
    assert [view["lens"] for view in projections] == ["Rescue", "Diagnose", "Verify"]


def test_projection_rejects_an_unknown_lens_without_mutating_the_journey():
    journey = append_event(_journey(), _event("decomposed", claims=[_claim()]))
    original = deepcopy(journey)
    with pytest.raises(ValueError, match="lens"):
        project_journey(journey, lens="summary")
    assert journey == original


def test_claim_statement_cannot_be_rebound_when_its_verdict_changes():
    journey = append_event(_journey(), _event("decomposed", claims=[_claim()]))
    changed = _claim("PASS", statement="A different claim")
    with pytest.raises(ValueError, match="statement"):
        append_event(journey, _event("preflight", claims=[changed]))


def test_deep_acyclic_claim_graph_verifies_without_recursion_failure():
    claims = [
        _claim(
            claim_id=f"claim-{index}", statement=f"Claim {index}",
            depends_on=[] if index == 0 else [f"claim-{index - 1}"],
        )
        for index in reversed(range(1500))
    ]
    journey = append_event(_journey(), _event("decomposed", claims=claims))
    assert verify_journey(journey)["verdict"] == "PASS"
