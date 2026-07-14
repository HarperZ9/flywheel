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


def test_empty_store_is_an_honest_null(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    doc = comprehension_ledger()
    assert doc["files"] == {}
    assert "no checked evidence" in doc["note"]
