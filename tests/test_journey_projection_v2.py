from copy import deepcopy

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_projection import new_genesis, project_lens, reduce_events


EVENT_KEYS = {
    "schema", "journey_ref", "sequence", "event_type", "occurred_at",
    "actor_id", "request_sha256", "payload", "prior_event_sha256", "event_sha256",
}


def _event(ref, sequence, event_type, payload, prior=None):
    event = {
        "schema": "flywheel.evidence-journey-event/v2", "journey_ref": ref,
        "sequence": sequence, "event_type": event_type,
        "occurred_at": f"2026-08-14T12:0{sequence}:00Z", "actor_id": "owner-1",
        "request_sha256": canonical_sha256({"request": sequence}),
        "payload": payload, "prior_event_sha256": prior,
    }
    return {**event, "event_sha256": canonical_sha256(event)}


def _genesis():
    return new_genesis(
        journey_ref="jrn_0123456789abcdef0123456789abcdef", legacy_label="repair-1",
        goal="Explain the failed verification", intake={"receipt_refs": ["receipt:intake"]},
        actor_id="owner-1", occurred_at="2026-08-14T12:00:00Z",
    )


def test_new_genesis_emits_the_exact_hash_bound_event_contract():
    """A missing sealed genesis field must not be accepted as a durable event."""
    event = _genesis()
    assert set(event) == EVENT_KEYS
    assert event["schema"] == "flywheel.evidence-journey-event/v2"
    assert event["sequence"] == 0 and event["event_type"] == "intake"
    assert event["prior_event_sha256"] is None
    assert event["payload"] == {
        "legacy_label": "repair-1", "goal": "Explain the failed verification",
        "intake": {"receipt_refs": ["receipt:intake"]},
    }
    assert event["event_sha256"] == canonical_sha256(
        {key: value for key, value in event.items() if key != "event_sha256"},
    )


def test_reducer_enforces_stage_order_and_keeps_operational_events_in_stage():
    """A skipped stage or an operational stage advance must fail reduction."""
    genesis = _genesis()
    decomposed = _event(genesis["journey_ref"], 1, "decomposed", {}, genesis["event_sha256"])
    fact = _event(genesis["journey_ref"], 2, "record_fact", {
        "facts": [{
            "fact_id": "fact-intake", "statement": "The intake receipt exists.",
            "receipt_refs": ["receipt:intake"], "receipt_state": "MATCH",
            "does_not_prove": "That the requested repair is correct.",
        }],
    }, decomposed["event_sha256"])
    projection = reduce_events([genesis, decomposed, fact])
    assert projection["stage"] == "decomposed"
    skipped = _event(genesis["journey_ref"], 1, "preflight", {}, genesis["event_sha256"])
    with pytest.raises(ValueError, match="stage"):
        reduce_events([genesis, skipped])
    forged = deepcopy(fact)
    forged["event_type"] = "running"
    forged["event_sha256"] = canonical_sha256(
        {key: value for key, value in forged.items() if key != "event_sha256"},
    )
    with pytest.raises(ValueError, match="stage"):
        reduce_events([genesis, decomposed, forged])


def test_reducer_rejects_changed_fact_or_claim_definitions_and_bad_receipt_states():
    """Redefinition or an unrecognised receipt state must never rewrite evidence."""
    genesis = _genesis()
    fact = _event(genesis["journey_ref"], 1, "record_fact", {
        "facts": [{
            "fact_id": "fact-1", "statement": "Input receipt exists.",
            "receipt_refs": ["receipt:intake"], "receipt_state": "MATCH",
            "does_not_prove": "The conclusion is true.",
        }],
    }, genesis["event_sha256"])
    claim = _event(genesis["journey_ref"], 2, "record_claim", {
        "claims": [{
            "claim_id": "claim-1", "statement": "The failure reproduces.",
            "depends_on": ["fact-1"], "receipt_refs": ["receipt:intake"],
            "receipt_state": "MATCH", "verdict": "UNDECIDED",
            "does_not_prove": "The repair has succeeded.",
        }],
    }, fact["event_sha256"])
    revised = _event(genesis["journey_ref"], 3, "record_fact", {
        "facts": [{
            "fact_id": "fact-1", "statement": "Different input receipt exists.",
            "receipt_refs": ["receipt:intake"], "receipt_state": "MATCH",
            "does_not_prove": "The conclusion is true.",
        }],
    }, claim["event_sha256"])
    with pytest.raises(ValueError, match="immutable"):
        reduce_events([genesis, fact, claim, revised])
    malformed = deepcopy(fact)
    malformed["payload"]["facts"][0]["receipt_state"] = "VALID"
    malformed["event_sha256"] = canonical_sha256(
        {key: value for key, value in malformed.items() if key != "event_sha256"},
    )
    with pytest.raises(ValueError, match="receipt_state"):
        reduce_events([genesis, malformed])


def test_all_lenses_preserve_evidence_facts_and_only_reorder_presentation():
    """A lens must not alter the evidence facts it presents."""
    genesis = _genesis()
    claim = _event(genesis["journey_ref"], 1, "record_claim", {
        "claims": [{
            "claim_id": "claim-1", "statement": "The failure reproduces.",
            "depends_on": [], "receipt_refs": ["receipt:intake"],
            "receipt_state": "MATCH", "verdict": "FAIL",
            "does_not_prove": "The repair has succeeded.",
        }],
        "checks": [{
            "check_id": "check-1", "claim_id": "claim-1", "verdict": "FAIL",
            "receipt_refs": ["receipt:intake"], "receipt_state": "MATCH",
            "numerator": 1, "denominator": 1,
            "does_not_prove": "The cause is known.",
        }],
    }, genesis["event_sha256"])
    projection = reduce_events([genesis, claim])
    views = [project_lens(projection, lens) for lens in ("rescue", "diagnose", "verify")]
    keys = (
        "journey_ref", "event_head_sha256", "fact_ids", "claim_ids", "checks",
        "verdicts", "missing_evidence", "stage", "conclusion",
    )
    assert [{key: view[key] for key in keys} for view in views] == [
        {key: views[0][key] for key in keys},
    ] * 3
    assert [view["lens"] for view in views] == ["Rescue", "Diagnose", "Verify"]
    assert [tuple(view["presentation"]) for view in views] == [
        ("next_actions", "claims", "checks", "facts"),
        ("claims", "checks", "facts", "next_actions"),
        ("checks", "facts", "claims", "next_actions"),
    ]
