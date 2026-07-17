"""Builds 9 and 10: retention receipts separate what was once demonstrated
from what is still held (a retest is unaided by design), and TTVA is only
ever earned by a trusted green run — felt speed is inadmissible, and an
unverified run's TTVA is an honest null."""

from harness.retention import retention_due, retention_record
from harness.router_agent import run_router_agent
from harness.store import put_entity


class _Out:
    def __init__(self, text):
        self.text = text
        self.model_ref = "stub"
        self.seed = 0


class _Stub:
    def __init__(self, script):
        self.script = list(script)

    def generate(self, prompt, *, seed, temperature, max_new_tokens,
                 system=""):
        return _Out(self.script.pop(0) if self.script else "done.")


def _bank_original(eid="c1"):
    put_entity("comprehension", {"passed": True, "reviewer": "learner",
                                 "key_terms": ["tax", "subtotal"],
                                 "files": ["a.py"]}, eid=eid)


def test_due_then_recorded_then_not_due(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    _bank_original("c1")
    doc = retention_due(days=0)
    assert [d["eid"] for d in doc["due"]] == ["c1"]
    assert "unaided by design" in doc["note"]
    receipt = retention_record("c1", "i could not repair it unaided",
                               waive_interval_reason="test probe")
    assert receipt["passed"] is False       # graded: the answer misses the terms
    assert receipt["coverage"] == 0.0
    assert receipt["stored"]
    assert retention_due(days=0)["due"] == []


def test_immediate_retest_without_waiver_is_refused(monkeypatch, tmp_path):
    # 'Held is what survives the retest' is mintable in the same second
    # without an interval gate; spacing IS the mechanism.
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    _bank_original("c1")
    r = retention_record("c1", "a.py applies tax to the subtotal")
    assert "error" in r and "soon" in r["error"]


def test_self_declared_boolean_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    _bank_original("c1")
    r = retention_record("c1", True, waive_interval_reason="test probe")
    assert "error" in r and "graded" in r["error"]


def test_waived_retest_is_graded_and_the_waiver_is_declared(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    _bank_original("c1")
    good = retention_record("c1", "a.py now applies tax to the subtotal",
                            waive_interval_reason="loop-closure probe")
    assert good["passed"] is True
    assert good["coverage"] >= 0.6
    assert good["waived_interval"] == "loop-closure probe"


def test_original_without_key_material_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    put_entity("comprehension", {"passed": True, "files": ["a.py"]}, eid="bare")
    r = retention_record("bare", "anything", waive_interval_reason="test")
    assert "error" in r and "material" in r["error"]


def test_recording_against_nothing_is_a_named_error(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    assert "error" in retention_record("ghost", "an answer")


def test_ttva_is_null_without_a_trusted_green_run(tmp_path):
    stub = _Stub(['TOOL write_file {"path": "x.py", "content": "a = 1\\n"}',
                  "wrote it."])
    out = run_router_agent("write x", endpoint="anything",
                           root=str(tmp_path), proposer=stub,
                           allow_write=True, max_steps=4)
    assert out["duration_s"] >= 0
    assert out["ttva_s"] is None  # nothing verified, nothing claimed
    # provenance rides the run: the model authored x.py, bound to the run
    rows = {r["path"]: r for r in out["provenance"]["attributions"]}
    assert rows["x.py"]["author"] == "model:anything"
    assert out["provenance"]["conversation"] == out["checkpoint"]
