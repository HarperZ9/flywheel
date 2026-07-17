"""The comprehension ledger: ownership computed from checked evidence, not
git blame — the substrate-collapse replacement. Only a COMPLETE attestation
or a PASSED comprehension receipt confers holdership; partial walks and
failed gates never do, and the latest evidence wins per file."""

from harness.comprehension_ledger import SCHEMA, comprehension_ledger
from harness.store import put_entity


def _seed(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    put_entity("attestation", {
        "standing": "complete", "reviewer": "papacr0w",
        "reviewed": ["a.py", "b.py"], "coverage": 1.0}, eid="att-new")
    put_entity("attestation", {
        "standing": "partial", "reviewer": "rushed",
        "reviewed": ["c.py"], "coverage": 0.4}, eid="att-partial")
    put_entity("comprehension", {
        "passed": True, "reviewer": "learner",
        "files": ["d.py"], "coverage": 0.8}, eid="comp-pass")
    put_entity("comprehension", {
        "passed": False, "reviewer": "vague",
        "files": ["e.py"], "coverage": 0.1}, eid="comp-fail")


def test_only_checked_evidence_confers_holdership(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    doc = comprehension_ledger()
    assert doc["schema"] == SCHEMA
    assert doc["files"]["a.py"]["holder"] == "papacr0w"
    assert doc["files"]["a.py"]["kind"] == "attestation"
    assert doc["files"]["d.py"]["holder"] == "learner"
    assert "c.py" not in doc["files"], "partial coverage confers nothing"
    assert "e.py" not in doc["files"], "a failed gate confers nothing"
    assert doc["holders"]["papacr0w"] == 2


def test_newer_comprehension_beats_older_attestation_across_kinds(
        monkeypatch, tmp_path):
    """The docstring promises recency wins. An OLDER attestation must not
    permanently block a NEWER passed comprehension on the same file just
    because attestations are iterated first."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import harness.store as store
    clock = {"t": 100.0}
    monkeypatch.setattr(store.time, "time", lambda: clock["t"])
    clock["t"] = 1.0
    put_entity("attestation", {"standing": "complete", "reviewer": "early",
                               "reviewed": ["x.py"]}, eid="att-old")
    clock["t"] = 2.0
    put_entity("comprehension", {"passed": True, "reviewer": "later",
                                 "files": ["x.py"]}, eid="comp-new")
    doc = comprehension_ledger()
    assert doc["files"]["x.py"]["holder"] == "later", \
        "the newer comprehension must hold x.py, not the older attestation"
    assert doc["files"]["x.py"]["kind"] == "comprehension"


def test_older_comprehension_does_not_beat_newer_attestation(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import harness.store as store
    clock = {"t": 100.0}
    monkeypatch.setattr(store.time, "time", lambda: clock["t"])
    clock["t"] = 1.0
    put_entity("comprehension", {"passed": True, "reviewer": "early",
                                 "files": ["y.py"]}, eid="comp-old")
    clock["t"] = 2.0
    put_entity("attestation", {"standing": "complete", "reviewer": "later",
                               "reviewed": ["y.py"]}, eid="att-new")
    doc = comprehension_ledger()
    assert doc["files"]["y.py"]["holder"] == "later"
    assert doc["files"]["y.py"]["kind"] == "attestation"


def test_empty_store_is_an_honest_null(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    doc = comprehension_ledger()
    assert doc["files"] == {}
    assert "no checked evidence" in doc["note"]


def test_same_file_merges_across_path_spellings(monkeypatch, tmp_path):
    """Basename-vs-path and slash-form splits must not defeat the cross-kind
    merge: one file, one row, newest evidence holds it."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import harness.store as store
    clock = {"t": 1.0}
    monkeypatch.setattr(store.time, "time", lambda: clock["t"])
    put_entity("attestation", {"standing": "complete", "reviewer": "early",
                               "reviewed": ["harness\store.py"]}, eid="att")
    clock["t"] = 2.0
    put_entity("comprehension", {"passed": True, "reviewer": "later",
                                 "files": ["harness/store.py"]}, eid="comp")
    doc = comprehension_ledger()
    assert doc["files"]["harness/store.py"]["holder"] == "later"
    assert "harness\store.py" not in doc["files"]


def test_failed_retest_decays_holdership(monkeypatch, tmp_path):
    """retention.py promises the ledger distinguishes what someone once
    demonstrated from what they still hold; a failed unaided retest must
    revoke the row, visibly."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    put_entity("comprehension", {"passed": True, "reviewer": "learner",
                                 "files": ["a.py"],
                                 "key_terms": ["tax", "subtotal"]}, eid="c1")
    from harness.retention import retention_record
    r = retention_record("c1", "no recall of any of it",
                         waive_interval_reason="test probe")
    assert r["passed"] is False
    doc = comprehension_ledger()
    assert "a.py" not in doc["files"]
    assert doc["decayed"]["a.py"]["eid"] == "c1"


def test_passed_retest_keeps_holdership(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    put_entity("comprehension", {"passed": True, "reviewer": "learner",
                                 "files": ["a.py"],
                                 "key_terms": ["tax", "subtotal"]}, eid="c1")
    from harness.retention import retention_record
    r = retention_record("c1", "a.py applies tax to the subtotal",
                         waive_interval_reason="test probe")
    assert r["passed"] is True
    doc = comprehension_ledger()
    assert doc["files"]["a.py"]["holder"] == "learner"
