"""Attestation is ownership made checkable: a sign-off bound to the run's
checkpoint and to exactly what the reviewer walked. Coverage is visible,
overclaims are flagged, and the whole thing is content-addressed so a
doctored attestation stops matching its own hash. And it binds to a BANKED
run: a fabricated run doc, or a review that does not hash to the banked
run's review_sha256, is refused, so a COMPLETE attestation cannot cover
files no run ever touched."""

import hashlib
import json

from harness.attestation import SCHEMA, attest, attest_banked

RUN = {
    "checkpoint": "abc123def456",
    "review": {
        "files_edited": ["a.py", "b.py", "c.py"],
        "files_read": ["a.py", "b.py", "c.py", "d.py"],
        "reviewability": 0.9,
    },
}


def test_a_run_that_edited_nothing_is_not_complete():
    """A run with zero edited files must not read 'complete' at coverage
    1.0: there is nothing to have reviewed, and a vacuous 'complete'
    would confer holdership in the ledger (tenet 4)."""
    empty = {"checkpoint": "x", "review": {"files_edited": []}}
    doc = attest(empty, [], reviewer="nobody")
    assert doc["standing"] != "complete"
    assert doc["standing"] == "empty"
    assert doc["coverage"] is None


def test_full_coverage_is_a_complete_attestation():
    doc = attest(RUN, ["a.py", "b.py", "c.py"], note="walked every diff",
                 reviewer="papacr0w")
    assert doc["schema"] == SCHEMA
    assert doc["coverage"] == 1.0
    assert doc["standing"] == "complete"
    assert doc["unreviewed"] == []
    assert doc["checkpoint"] == "abc123def456"
    assert len(doc["sha256"]) == 64


def test_partial_coverage_stays_visible():
    doc = attest(RUN, ["a.py"], reviewer="papacr0w")
    assert doc["coverage"] == round(1 / 3, 4)
    assert doc["standing"] == "partial"
    assert doc["unreviewed"] == ["b.py", "c.py"]


def test_overclaims_are_flagged_never_counted():
    doc = attest(RUN, ["a.py", "not-in-run.py"], reviewer="papacr0w")
    assert doc["coverage"] == round(1 / 3, 4)
    assert doc["overclaimed"] == ["not-in-run.py"]


def test_tampering_moves_the_hash():
    a = attest(RUN, ["a.py"], note="x", reviewer="r")
    b = attest(RUN, ["a.py"], note="y", reviewer="r")
    assert a["sha256"] != b["sha256"]
    # Same inputs, same hash: the attestation is re-derivable.
    assert attest(RUN, ["a.py"], note="x", reviewer="r")["sha256"] == a["sha256"]


def _bank_run(review):
    from harness.store import put_entity
    summary = {
        "checkpoint": "abc123def456",
        "review_sha256": hashlib.sha256(
            json.dumps(review, sort_keys=True).encode()).hexdigest(),
    }
    return put_entity("agent-run", summary)["eid"]


def test_fabricated_run_is_refused(monkeypatch, tmp_path):
    # No banked agent-run entity: nothing to attest against. A caller-supplied
    # run doc must never confer a 'complete' standing on its own say-so.
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    r = attest_banked("ghost-run", RUN["review"], ["a.py"])
    assert "error" in r and "banked" in r["error"]


def test_review_that_does_not_hash_to_the_banked_run_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    eid = _bank_run(RUN["review"])
    forged = dict(RUN["review"], files_edited=["harness/store.py"])
    r = attest_banked(eid, forged, ["harness/store.py"])
    assert "error" in r and "review_sha256" in r["error"]


def test_banked_run_with_matching_review_attests_and_names_the_run(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    eid = _bank_run(RUN["review"])
    doc = attest_banked(eid, RUN["review"], ["a.py", "b.py", "c.py"],
                        reviewer="papacr0w")
    assert doc["standing"] == "complete"
    assert doc["run_eid"] == eid
    assert doc["checkpoint"] == "abc123def456"
    # the run binding is inside the sealed content, not decoration
    redone = dict(doc)
    redone.pop("sha256")
    assert hashlib.sha256(
        json.dumps(redone, sort_keys=True).encode()).hexdigest() == doc["sha256"]
