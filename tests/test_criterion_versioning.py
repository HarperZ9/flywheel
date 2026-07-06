"""criterion-versioning falsifier — drift vs re-baseline are distinct.

The Red Queen (2606.26294) distinction: a MATCH under an old criterion is not a
MATCH under a new one. staleness_report must separate:
  - DRIFT grounding: an ancestor's CONTENT was refuted -> descendant is wrong
    (UNVERIFIABLE, reason "drifted ancestor");
  - REBASELINE grounding: an ancestor's CRITERION was intentionally upgraded since
    we verified -> descendant is not wrong, it is STALE and re-verifiable.
"""
from harness.transitive_witness import (
    DepNode, staleness_report, MATCH, DRIFT, UNVERIFIABLE, REBASELINE)


def test_upgraded_criterion_is_rebaseline_not_drift():
    # A is fine (local MATCH) but its criterion advanced to v2; B was verified
    # against A@v1. B is transitively MATCH, but STALE -> REBASELINE, not MATCH.
    nodes = [
        DepNode("A", local=MATCH, criterion_version=2),
        DepNode("B", local=MATCH, deps=["A"], dep_versions={"A": 1}),
    ]
    r = staleness_report(nodes)
    assert r["A"]["verdict"] == MATCH
    assert r["B"]["verdict"] == REBASELINE, r["B"]
    assert "re-verify" in r["B"]["reason"]


def test_fresh_criterion_is_plain_match():
    nodes = [
        DepNode("A", local=MATCH, criterion_version=2),
        DepNode("B", local=MATCH, deps=["A"], dep_versions={"A": 2}),  # verified against current
    ]
    r = staleness_report(nodes)
    assert r["B"]["verdict"] == MATCH


def test_drift_is_not_confused_with_rebaseline():
    # A's CONTENT drifted (local DRIFT). B is grounded-on-drift -> UNVERIFIABLE
    # with the drift reason, never REBASELINE.
    nodes = [
        DepNode("A", local=DRIFT, criterion_version=2),
        DepNode("B", local=MATCH, deps=["A"], dep_versions={"A": 1}),
    ]
    r = staleness_report(nodes)
    assert r["A"]["verdict"] == DRIFT
    assert r["B"]["verdict"] == UNVERIFIABLE
    assert "drifted" in r["B"]["reason"]


def test_reasons_are_specific():
    nodes = [
        DepNode("solo_no_receipt", local=MATCH, has_receipt=False),
        DepNode("dangling", local=MATCH, deps=["ghost"]),
        DepNode("clean", local=MATCH),
    ]
    r = staleness_report(nodes)
    assert r["solo_no_receipt"] == {"verdict": UNVERIFIABLE, "reason": "no receipt"}
    assert "dangling" in r["dangling"]["reason"]
    assert r["clean"]["verdict"] == MATCH


def test_versioning_defaults_are_backward_compatible():
    # a node with no version info recorded must never be spuriously REBASELINE
    nodes = [DepNode("A", local=MATCH), DepNode("B", local=MATCH, deps=["A"])]
    r = staleness_report(nodes)
    assert r["A"]["verdict"] == MATCH and r["B"]["verdict"] == MATCH
