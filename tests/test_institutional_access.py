import pytest

from harness.evidence_json import canonical_sha256
from harness.institutional_access import (
    InstitutionalAccessError,
    access_scope,
    assess_institutional_access,
)

SOURCES = {
    "task": {"expected_final_state": {"release": "HOLD", "status": "needs_review"}},
    "trace": {"final_state": {"release": "HOLD", "status": "needs_review"}},
}
CLAIMS = {"claim-final-state": ["task", "trace"]}
REVIEWER = {
    "role": "external_evaluator",
    "declared_conflicts": [],
    "relationship_to_producer": "unknown",
}


def scope(claims=None, sources=None):
    return access_scope("scope-1", claims or CLAIMS, sources or SOURCES)


def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)


def pointer(ref, path, value):
    return {"source_ref": ref, "json_pointer": path, "source_value": value}


def event(event_id, sequence, ref, status="granted", pointers=None, redactions=None):
    return {
        "event_id": event_id,
        "sequence": sequence,
        "evidence_ref": ref,
        "status": status,
        "stated_reason": f"{status} by fixture declaration",
        "source_pointers": pointers if pointers is not None else [pointer(ref, "", SOURCES[ref])],
        "redactions": redactions or [],
    }


def record(events, sc=None):
    sc = sc or scope()
    return {
        "schema": "flywheel.institutional-access/v1",
        "scope_sha256": sc["scope_sha256"],
        "reviewer": REVIEWER,
        "events": events,
    }


def test_complete_declared_access_is_coverage_not_semantic_support():
    report = assess_institutional_access(record([
        event("trace-grant", 2, "trace", pointers=[pointer("trace", "/final_state", SOURCES["trace"]["final_state"])]),
        event("task-grant", 1, "task", pointers=[pointer("task", "/expected_final_state", SOURCES["task"]["expected_final_state"])]),
    ]), scope=scope(), sources=SOURCES)

    assert report["schema"] == "flywheel.institutional-access-assessment/v1"
    assert report["coverage_assessment"] == "complete"
    assert report["claims"] == [{
        "claim_id": "claim-final-state",
        "coverage": "complete",
        "available_refs": ["task", "trace"],
        "limited_refs": [],
        "reasons": [],
    }]
    assert "support" not in set(keys(report))
    assert any("semantic" in item for item in report["does_not_prove"])


@pytest.mark.parametrize("status", ["requested", "denied", "unavailable", "unknown", "withdrawn"])
def test_non_granted_required_latest_status_limits_coverage(status):
    report = assess_institutional_access(record([
        event("task-grant", 1, "task"),
        event("trace-limited", 2, "trace", status=status, pointers=[]),
    ]), scope=scope(), sources=SOURCES)

    assert report["coverage_assessment"] == "limited"
    claim = report["claims"][0]
    assert claim["coverage"] == "limited"
    assert claim["available_refs"] == ["task"]
    assert claim["limited_refs"] == ["trace"]
    assert f"trace:{status}" in claim["reasons"]


def test_prior_denial_before_legitimate_grant_keeps_history_but_latest_is_complete():
    report = assess_institutional_access(record([
        event("grant", 3, "trace"),
        event("request", 1, "trace", status="requested", pointers=[]),
        event("deny", 2, "trace", status="denied", pointers=[]),
        event("task-grant", 4, "task"),
    ]), scope=scope(), sources=SOURCES)

    assert [item["event_id"] for item in report["events"]] == ["request", "deny", "grant", "task-grant"]
    assert report["latest_by_ref"] == [
        {"evidence_ref": "task", "event_id": "task-grant", "status": "granted"},
        {"evidence_ref": "trace", "event_id": "grant", "status": "granted"},
    ]
    assert report["coverage_assessment"] == "complete"


@pytest.mark.parametrize("impact", ["unknown", "blocks_verification"])
def test_unknown_or_blocking_redaction_limits_claim_despite_grant(impact):
    report = assess_institutional_access(record([
        event("task-grant", 1, "task"),
        event("trace-grant", 2, "trace", redactions=[{
            "redaction_id": "r1",
            "impact": impact,
            "stated_reason": "declared sensitive field removed",
        }]),
    ]), scope=scope(), sources=SOURCES)

    assert report["coverage_assessment"] == "limited"
    assert f"trace:redaction:{impact}" in report["claims"][0]["reasons"]


def test_source_pointer_value_mismatch_rejects_instead_of_limiting():
    bad = record([event("trace-grant", 1, "trace", pointers=[
        pointer("trace", "/final_state/status", "done")
    ])])

    with pytest.raises(InstitutionalAccessError, match="source pointer value"):
        assess_institutional_access(bad, scope=scope(), sources=SOURCES)


def test_scope_or_retained_source_drift_invalidates_binding():
    original = scope()
    changed_sources = {**SOURCES, "trace": {"final_state": {"release": "SHIP"}}}

    with pytest.raises(InstitutionalAccessError, match="source inventory"):
        assess_institutional_access(record([event("trace-grant", 1, "trace")], original),
                                    scope=original, sources=changed_sources)

    changed_scope = scope({"claim-final-state": ["task"]}, SOURCES)
    with pytest.raises(InstitutionalAccessError, match="scope_sha256"):
        assess_institutional_access(record([event("task-grant", 1, "task")], original),
                                    scope=changed_scope, sources=SOURCES)


def test_missing_component_is_no_access_assessment():
    assert assess_institutional_access(None, scope=scope(), sources=SOURCES) is None



def reseal_scope(doc):
    body = {key: doc[key] for key in ("schema", "scope_id", "claims", "source_inventory")}
    doc["scope_sha256"] = canonical_sha256(body)
    return doc


@pytest.mark.parametrize("mutate, message", [
    (lambda doc: doc.update({"claims": []}), "claims"),
    (lambda doc: doc["claims"][0].update({"required_refs": []}), "required_refs"),
    (lambda doc: doc.update({"claims": doc["claims"] + [dict(doc["claims"][0])]}), "duplicate"),
    (lambda doc: doc["claims"][0].update({"required_refs": ["trace", "trace"]}), "required_refs"),
    (lambda doc: doc["claims"][0].update({"required_refs": ["ghost"]}), "source inventory"),
])
def test_manual_resealed_scope_claim_malformed_forms_fail_closed(mutate, message):
    doc = scope()
    mutate(doc)
    reseal_scope(doc)

    with pytest.raises(InstitutionalAccessError, match=message):
        assess_institutional_access(record([], doc), scope=doc, sources=SOURCES)


def test_assessment_snapshots_pointer_source_values_against_later_mutation():
    sources = {"trace": {"final_state": {"release": "HOLD"}}}
    sc = scope({"claim": ["trace"]}, sources)
    source_value = sources["trace"]["final_state"]
    report = assess_institutional_access({
        "schema": "flywheel.institutional-access/v1",
        "scope_sha256": sc["scope_sha256"],
        "reviewer": REVIEWER,
        "events": [event("trace-grant", 1, "trace", pointers=[
            pointer("trace", "/final_state", source_value)
        ])],
    }, scope=sc, sources=sources)

    source_value["release"] = "SHIP"
    sources["trace"]["final_state"]["extra"] = "mutated"

    assert report["events"][0]["source_pointers"][0]["source_value"] == {"release": "HOLD"}


def test_json_pointer_rejects_invalid_escapes_and_array_indices():
    sources = {"trace": {"a/b": {"tilde~key": "ok"}, "bad~2key": "bad", "items": ["zero"]}}
    sc = scope({"claim": ["trace"]}, sources)
    good = record([event("trace-grant", 1, "trace", pointers=[
        pointer("trace", "/a~1b/tilde~0key", "ok")
    ])], sc)
    assert assess_institutional_access(good, scope=sc, sources=sources)["coverage_assessment"] == "complete"

    for bad_pointer in ("/bad~2key", "/items/00", "/items/x", "/items/1"):
        bad = record([event("trace-grant", 1, "trace", pointers=[
            pointer("trace", bad_pointer, "bad")
        ])], sc)
        with pytest.raises(InstitutionalAccessError, match="json_pointer"):
            assess_institutional_access(bad, scope=sc, sources=sources)
