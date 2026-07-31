"""The Phase 0 disproof gate.

One command must take the existing chain end to end: an exact symbolic oracle
disposes a group of candidate matmul schemes, the group is scored with the named
estimator, the accepted candidate is sealed into a proof envelope, and the
envelope is re-witnessed by re-running the same oracle over the stored candidate.

Every part already existed and was never wired together. If this cannot reach
MATCH, the premise that these parts compose is false, and Phase 0 has disproven
the plan for the price of one week.
"""
import json

from harness.gate import run_gate, rewitness_envelope


def test_gate_reaches_match(tmp_path):
    r = run_gate(tmp_path)
    assert r.verdict == "PASS"
    assert r.rewitness == "MATCH"


def test_gate_group_is_mixed_so_it_carries_a_gradient(tmp_path):
    r = run_gate(tmp_path)
    steps = {s["step"]: s for s in r.steps}
    collect = steps["collect"]
    assert collect["n_pass"] >= 1
    assert collect["n_pass"] < collect["group_size"]
    assert collect["learnable"] is True


def test_gate_group_used_one_temperature_and_the_named_estimator(tmp_path):
    r = run_gate(tmp_path)
    steps = {s["step"]: s for s in r.steps}
    assert steps["collect"]["temperature"] > 0.0
    assert steps["collect"]["estimator"] == "drgrpo"


def test_gate_verify_step_attributes_to_the_candidate(tmp_path):
    r = run_gate(tmp_path)
    steps = {s["step"]: s for s in r.steps}
    assert steps["verify"]["verdict"] == "PASS"
    assert steps["verify"]["attribution"] == "CANDIDATE"


def test_gate_writes_an_envelope_and_a_report(tmp_path):
    r = run_gate(tmp_path)
    assert (tmp_path / "gate_envelope.json").exists()
    assert (tmp_path / "gate_report.json").exists()
    assert len(r.envelope_hash) == 16
    assert len(r.claim_hash) == 16


def test_a_tampered_verdict_fails_to_rewitness(tmp_path):
    run_gate(tmp_path)
    p = tmp_path / "gate_envelope.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["verdict"] = "FAIL" if d["verdict"] == "PASS" else "PASS"
    p.write_text(json.dumps(d, indent=2, sort_keys=True), encoding="utf-8")
    assert rewitness_envelope(p) == "DRIFT"


def test_a_tampered_candidate_fails_to_rewitness(tmp_path):
    run_gate(tmp_path)
    p = tmp_path / "gate_envelope.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["candidate"] = '{"n":2,"m":2,"p":2,"triples":[]}'
    p.write_text(json.dumps(d, indent=2, sort_keys=True), encoding="utf-8")
    assert rewitness_envelope(p) == "DRIFT"


def test_a_missing_envelope_is_unverifiable_never_match(tmp_path):
    assert rewitness_envelope(tmp_path / "does_not_exist.json") == "UNVERIFIABLE"


def test_a_malformed_envelope_is_unverifiable_never_match(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json at all", encoding="utf-8")
    assert rewitness_envelope(p) == "UNVERIFIABLE"


def test_gate_is_deterministic(tmp_path):
    a = run_gate(tmp_path / "a")
    b = run_gate(tmp_path / "b")
    assert a.group_signal_hash == b.group_signal_hash
    assert a.envelope_hash == b.envelope_hash
    assert a.claim_hash == b.claim_hash
