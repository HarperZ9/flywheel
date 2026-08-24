"""Frontier claims: the lossless claim record and the four-axis
projection. Identification, verification, policy, and value stay
independent objects with independent hashes; no composite score exists,
unknown raw values round-trip verbatim, and NOT_FOUND_IN_CORPUS is never
translated into novelty."""
import pytest

from harness.frontier_claim import new_frontier_claim
from harness.frontier_claim_projection import (
    AXES,
    append_frontier_axis_event,
    project_frontier_axes,
)

SOURCE = {
    "title": "On Verifier-First Agents",
    "authors": ["A. Checker"],
    "year": 2026,
    "url": "https://example.org/paper",
    "source_id": "src_" + "a" * 8,
}
PROPOSITION = {
    "statement": "verifier-first harnesses beat raw scale on gated tasks",
    "domain": "agentic-code",
}


def _claim(**over):
    kwargs = dict(
        claim_id="clm_" + "a" * 8,
        journey_ref="jrn_" + "a" * 32,
        source=SOURCE,
        proposition=PROPOSITION,
        created_at="2026-08-22T12:00:00Z",
    )
    kwargs.update(over)
    return new_frontier_claim(**kwargs)


def test_claim_schema_and_sha():
    claim = _claim()
    assert claim["schema"] == "flywheel.frontier-claim/v1"
    assert claim["claim_sha256"]


def test_identification_owns_source_proposition_authorship():
    claim = _claim()
    assert claim["identification"]["source"] == SOURCE
    assert claim["identification"]["proposition"] == PROPOSITION
    assert claim["identification"]["created_at"] == "2026-08-22T12:00:00Z"


def test_legacy_fields_round_trip_losslessly():
    legacy = {
        "review_state": "under_review",
        "verdict": None,
        "evidence_kind": "benchmark",
        "community_state": "unreviewed",
        "novelty_state": "NOT_FOUND_IN_CORPUS",
        "fidelity_state": None,
        "freshness_state": "stale",
        "reproduction_state": "unattempted",
    }
    claim = _claim(**legacy)
    axes = project_frontier_axes(
        claim=claim, journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64)
    by_name = {a["axis"]: a for a in axes["axes"]}
    verification = by_name["verification"]["fields"]
    assert verification["verdict"] is None
    assert verification["freshness_state"] == "stale"
    policy = by_name["policy"]["fields"]
    assert policy["review_state"] == "under_review"
    assert policy["community_state"] == "unreviewed"
    value = by_name["value"]["fields"]
    assert value["novelty_state"] == "NOT_FOUND_IN_CORPUS"
    # NOT_FOUND_IN_CORPUS stays exactly what it is: not found, not novel.
    assert value["novelty_state"] != "novel"


def test_axes_are_independently_hashed():
    legacy = dict(
        review_state="under_review",
        verdict=None,
        evidence_kind="benchmark",
        community_state="unreviewed",
        novelty_state="NOT_FOUND_IN_CORPUS",
        fidelity_state=None,
        freshness_state="stale",
        reproduction_state="unattempted",
    )
    axes = project_frontier_axes(
        claim=_claim(**legacy), journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64)
    hashes = {a["axis"]: a["fields_sha256"] for a in axes["axes"]}
    assert len(set(hashes.values())) == len(AXES)


def test_no_composite_score_anywhere():
    axes = project_frontier_axes(
        claim=_claim(), journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64)

    def scan(value):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                for banned in ("composite", "score", "trust_index",
                               "overall"):
                    assert banned not in lowered, (banned, key)
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(axes)


def test_unknown_raw_values_preserve_as_invalid_response_facts():
    claim = _claim(novelty_state="SOME_FUTURE_STATE")
    axes = project_frontier_axes(
        claim=_claim(), journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64)

    def scan(value):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                for banned in ("composite", "score", "trust_index",
                               "overall"):
                    assert banned not in lowered, (banned, key)
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(axes)


def test_a_malformed_head_is_refused():
    with pytest.raises(ValueError):
        project_frontier_axes(claim=_claim(), journey_ref="jrn_" + "a" * 32,
                              event_head_sha256="not-a-head")


def test_wrong_journey_is_refused():
    with pytest.raises(ValueError):
        project_frontier_axes(claim=_claim(), journey_ref="jrn_" + "b" * 32,
                              event_head_sha256="a" * 64)


def test_cross_axis_mutation_is_refused():
    with pytest.raises(ValueError):
        append_frontier_axis_event(
            owner_ref="owner_" + "a" * 32, journey_ref="jrn_" + "a" * 32,
            expected_event_head="a" * 64, client_request_id="req-1",
            grant_ref="gnt_" + "a" * 32, claim_id="clm_" + "a" * 8,
            axis="identification", patch={"novelty_state": "novel"})


def test_stale_grant_or_head_is_refused():
    with pytest.raises(ValueError):
        append_frontier_axis_event(
            owner_ref="owner_" + "a" * 32, journey_ref="jrn_" + "a" * 32,
            expected_event_head="", client_request_id="req-1",
            grant_ref="", claim_id="clm_" + "a" * 8,
            axis="verification", patch={"verdict": "supported"})


def test_inferred_novelty_is_refused():
    with pytest.raises(ValueError):
        append_frontier_axis_event(
            owner_ref="owner_" + "a" * 32, journey_ref="jrn_" + "a" * 32,
            expected_event_head="a" * 64, client_request_id="req-1",
            grant_ref="gnt_" + "a" * 32, claim_id="clm_" + "a" * 8,
            axis="value", patch={"novelty_state": "inferred"})
