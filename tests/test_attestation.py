"""Attestation is ownership made checkable: a sign-off bound to the run's
checkpoint and to exactly what the reviewer walked. Coverage is visible,
overclaims are flagged, and the whole thing is content-addressed so a
doctored attestation stops matching its own hash."""

from harness.attestation import SCHEMA, attest

RUN = {
    "checkpoint": "abc123def456",
    "review": {
        "files_edited": ["a.py", "b.py", "c.py"],
        "files_read": ["a.py", "b.py", "c.py", "d.py"],
        "reviewability": 0.9,
    },
}


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
