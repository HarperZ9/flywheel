from copy import deepcopy
import pytest
from harness.evidence_journey import append_event, new_journey, project_journey, verify_journey

STAGES = ("intake", "decomposed", "preflight", "running", "concluded", "exported")
KINDS = ("inspect", "rerun", "collect", "escalate", "repair", "rollback", "recheck", "export")

def _journey(intake=None):
    return new_journey(
        journey_id="journey-1", goal="Explain and repair the failure",
        intake=intake or {"summary": "test failed", "receipt_refs": ["receipt:intake"]},
        created_at="2026-08-12T12:00:00Z",
    )

def _event(stage="decomposed", **fields):
    return {"stage": stage, "occurred_at": "2026-08-12T12:01:00Z", **fields}

def _claim(verdict="UNDECIDED", **fields):
    claim = {
        "claim_id": "claim-root", "statement": "The failure is reproducible",
        "depends_on": [], "verdict": verdict, "receipt_refs": ["receipt:root"], **fields,
    }
    if verdict in {"UNDECIDED", "UNVERIFIABLE"}:
        claim.setdefault("reason", "checker has not run")
    return claim

def _action(action_id="inspect", **fields):
    return {
        "action_id": action_id, "kind": "inspect", "description": "Inspect evidence",
        "basis_refs": ["receipt:intake"], **fields,
    }

def _advance(journey, target):
    for stage in STAGES[STAGES.index(journey["stage"]) + 1:STAGES.index(target) + 1]:
        journey = append_event(journey, _event(stage))
    return journey

def _nested(depth):
    value = "leaf"
    for _ in range(depth):
        value = {"child": value}
    return value

def _reject(event, message):
    with pytest.raises(ValueError, match=message):
        append_event(_journey(), event)

def test_new_journey_has_exact_schema_and_copies_intake():
    intake = {"summary": "failed", "nested": {"attempt": 1}}
    journey = _journey(intake)
    assert journey["schema"] == "flywheel.evidence-journey/v1"
    assert journey["stage"] == "intake"
    assert journey["events"] == [] and journey["event_head_sha256"] is None
    intake["nested"]["attempt"] = 2
    assert journey["intake"]["nested"]["attempt"] == 1

@pytest.mark.parametrize("stage", ["intake", "preflight", "INTAKE", "unknown"])
def test_state_machine_rejects_invalid_transition(stage):
    _reject(_event(stage), "transition|stage")

def test_state_machine_accepts_only_exact_stage_order():
    journey = _advance(_journey(), "exported")
    assert [event["stage"] for event in journey["events"]] == list(STAGES[1:])
    assert journey["stage"] == "exported"

def test_append_copies_inputs_and_binds_prior_hash():
    journey, event = _journey(), _event(claims=[_claim()])
    original_journey, original_event = deepcopy(journey), deepcopy(event)
    decomposed = append_event(journey, event)
    preflight = append_event(decomposed, _event("preflight"))
    assert journey == original_journey and event == original_event
    assert decomposed["events"][0]["prior_event_sha256"] is None
    assert preflight["events"][1]["prior_event_sha256"] == decomposed["event_head_sha256"]
    assert preflight["event_head_sha256"] == preflight["events"][1]["event_sha256"]

def test_append_isolates_stored_event_from_later_nested_mutation():
    event = _event(claims=[_claim(evidence={"steps": ["reproduce"]})])
    journey = append_event(_journey(), event)
    event["claims"][0]["evidence"]["steps"].append("rewrite")
    assert journey["events"][0]["claims"][0]["evidence"]["steps"] == ["reproduce"]
    assert verify_journey(journey)["verdict"] == "PASS"

def test_verifier_rejects_content_order_and_stored_head_tampering():
    content = _advance(_journey(), "preflight")
    content["events"][0]["occurred_at"] = "2026-08-12T12:59:00Z"
    order = _advance(_journey(), "running")
    order["events"][0], order["events"][1] = order["events"][1], order["events"][0]
    head = append_event(_journey(), _event())
    head["event_head_sha256"] = "0" * 64
    assert all(verify_journey(item)["verdict"] == "FAIL" for item in (content, order, head))
    assert "head" in verify_journey(head)["reason"]
    with pytest.raises(ValueError, match="head"):
        project_journey(head, lens="verify")

def test_stale_preceding_valid_event_head_rejects():
    journey = _advance(_journey(), "preflight")
    journey["event_head_sha256"] = journey["events"][-2]["event_sha256"]
    result = verify_journey(journey)
    assert result["verdict"] == "FAIL" and "head" in result["reason"]
    with pytest.raises(ValueError, match="head"):
        project_journey(journey, lens="verify")

@pytest.mark.parametrize("claims,message", [
    ([_claim(depends_on=["missing"])], "missing"),
    ([_claim(depends_on=["claim-root"])], "cycle"),
    ([_claim(depends_on=["child"]), _claim(claim_id="child", depends_on=["claim-root"])], "cycle"),
])
def test_claim_graph_rejects_missing_nodes_and_cycles_atomically(claims, message):
    journey = _journey()
    with pytest.raises(ValueError, match=message):
        append_event(journey, _event(claims=claims))
    assert journey["events"] == []

@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"])
def test_claims_accept_exact_four_way_verdicts(verdict):
    journey = append_event(_journey(), _event(claims=[_claim(verdict)]))
    assert project_journey(journey, lens="verify")["verdicts"] == {"claim-root": verdict}

def test_claims_reject_unknown_verdict_and_reasonless_honest_null():
    _reject(_event(claims=[_claim("MATCH")]), "verdict")
    claim = _claim("UNDECIDED")
    del claim["reason"]
    _reject(_event(claims=[claim]), "reason")

@pytest.mark.parametrize("metric", [
    {"metric_id": "latency", "value": None, "denominator": 0},
    {"metric_id": "rate", "value": True, "numerator": 1, "denominator": 1},
    {"metric_id": "rate", "value": 1.0, "numerator": True, "denominator": 1},
    {"metric_id": "rate", "value": 1.0, "numerator": 1, "denominator": True},
    {"metric_id": "rate", "value": None, "reason": "none", "numerator": -1, "denominator": 1},
    {"metric_id": "rate", "value": None, "reason": "none", "numerator": 0, "denominator": -1},
    {"metric_id": "rate", "value": 0.5, "numerator": 2, "denominator": 3},
    {"metric_id": "rate", "value": 1.5, "numerator": 3, "denominator": 2},
])
def test_metrics_reject_dishonest_nulls_booleans_negative_or_inconsistent_counts(metric):
    _reject(_event(metrics=[metric]), "reason|metric|numerator|denominator")

def test_reused_denominator_id_keeps_one_denominator():
    journey = append_event(_journey(), _event(metrics=[{
        "metric_id": "covered", "value": .5, "numerator": 1,
        "denominator": 2, "denominator_id": "cases",
    }]))
    with pytest.raises(ValueError, match="denominator"):
        append_event(journey, _event("preflight", metrics=[{
            "metric_id": "covered", "value": .5, "numerator": 2,
            "denominator": 4, "denominator_id": "cases",
        }]))

@pytest.mark.parametrize("field", ["metrics", "attestations", "claims", "next_actions"])
def test_event_collections_require_exact_lists(field):
    _reject(_event(**{field: {}}), field)

def _attestation(**fields):
    return {
        "subject": "claim-root", "role": "reviewer", "scope": ["statement"],
        "basis": ["receipt:root"], "issued_at": "2026-08-12T11:00:00Z",
        "expires_at": "2026-08-12T13:00:00Z", "signature_state": "unsigned", **fields,
    }

@pytest.mark.parametrize("field", ["subject", "role", "scope", "basis", "issued_at", "expires_at"])
def test_attestations_require_identity_scope_basis_and_times(field):
    attestation = _attestation()
    del attestation[field]
    _reject(_event(attestations=[attestation]), field)

def test_unsigned_expired_and_type_confused_attestations_reject():
    cases = [
        (_attestation(requires_signature=True), "signed"),
        (_attestation(requires_signature="true"), "requires_signature"),
        (_attestation(expires_at="2026-08-12T12:00:30Z", requires_active=True), "expired"),
    ]
    for attestation, message in cases:
        _reject(_event(attestations=[attestation]), message)

def test_active_signed_attestation_and_string_scope_basis_pass():
    signed = _attestation(
        signature_state="signed", signature="ed25519:abc",
        requires_signature=True, requires_active=True,
    )
    for attestation in (signed, _attestation(scope="claim", basis="receipt:root")):
        assert verify_journey(append_event(
            _journey(), _event(attestations=[attestation]),
        ))["verdict"] == "PASS"

@pytest.mark.parametrize("action,message", [
    (_action(basis_refs=[]), "basis_refs"),
    (_action(basis_refs=["receipt:unknown"]), "unresolved"),
    (_action(basis_refs=["claim-later"]), "unresolved"),
    (_action("inspect", basis_refs=["inspect"]), "self"),
])
def test_action_basis_rejects_empty_unknown_forward_and_self_refs(action, message):
    _reject(_event(next_actions=[action]), message)

def test_action_basis_can_cite_current_claim_and_receipt():
    journey = append_event(_journey(), _event(
        claims=[_claim()], next_actions=[_action(basis_refs=["claim-root", "receipt:root"])],
    ))
    assert verify_journey(journey)["verdict"] == "PASS"

@pytest.mark.parametrize("kind", KINDS)
def test_action_kind_vocabulary(kind):
    journey = append_event(_journey(), _event(next_actions=[_action(kind=kind)]))
    assert verify_journey(journey)["verdict"] == "PASS"

@pytest.mark.parametrize("extra", [
    {"operation": "replace", "path": "/claims/claim-root/verdict"},
    {"patch": {"op": "replace", "path": "/claims/claim-root/verdict"}},
    {"updates": {"claim-root": {"verdict": "PASS"}}}, {"claim_verdict": "PASS"},
])
def test_action_closed_schema_rejects_mutation_aliases(extra):
    _reject(_event(next_actions=[_action(**extra)]), "unknown")

def test_action_rejects_unknown_kind_and_redefinition():
    _reject(_event(next_actions=[_action(kind="replace")]), "kind")
    journey = append_event(_journey(), _event(next_actions=[_action("inspect")]))
    with pytest.raises(ValueError, match="immutable"):
        append_event(journey, _event("preflight", next_actions=[_action("inspect", kind="repair")]))

def test_three_lenses_preserve_identical_evidence_facts():
    journey = append_event(_journey(), _event(
        claims=[_claim("FAIL", reason="reproduced")],
        next_actions=[_action(basis_refs=["receipt:root"])],
    ))
    views = [project_journey(journey, lens=lens) for lens in ("rescue", "diagnose", "verify")]
    keys = ("journey_id", "event_head_sha256", "claim_ids", "verdicts", "receipt_refs")
    assert [{key: view[key] for key in keys} for view in views] == [
        {key: views[0][key] for key in keys},
    ] * 3
    assert [view["lens"] for view in views] == ["Rescue", "Diagnose", "Verify"]

def test_projection_rejects_unknown_lens_without_mutation():
    journey = append_event(_journey(), _event(claims=[_claim()]))
    original = deepcopy(journey)
    with pytest.raises(ValueError, match="lens"):
        project_journey(journey, lens="summary")
    assert journey == original

def test_claim_statement_is_immutable_across_verdict_updates():
    journey = append_event(_journey(), _event(claims=[_claim()]))
    with pytest.raises(ValueError, match="statement"):
        append_event(journey, _event("preflight", claims=[_claim("PASS", statement="different")]))

def test_deep_acyclic_claim_graph_avoids_recursion_failure():
    claims = [
        _claim(claim_id=f"c-{i}", statement=f"Claim {i}", depends_on=[] if i == 0 else [f"c-{i-1}"])
        for i in reversed(range(1500))
    ]
    assert verify_journey(append_event(_journey(), _event(claims=claims)))["verdict"] == "PASS"

def test_depth_guard_rejects_before_copy_or_hash_and_verifier_fails_typed():
    with pytest.raises(ValueError, match="depth"):
        _journey({"deep": _nested(1000)})
    with pytest.raises(ValueError, match="depth"):
        append_event(_journey(), _event(payload=_nested(1000)))
    journey = _journey()
    journey["intake"]["deep"] = _nested(1000)
    assert verify_journey(journey)["verdict"] == "FAIL"
    assert "depth" in verify_journey(journey)["reason"]

def test_depth_guard_allows_shared_acyclic_values():
    shared = ["receipt"]
    journey = _journey({"left": shared, "right": shared})
    assert verify_journey(journey)["verdict"] == "PASS"
