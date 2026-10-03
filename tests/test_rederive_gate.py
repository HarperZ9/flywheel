"""Re-derivation gate with a standard-error luck margin (preview).

Fixture: per-seed test F1 from experiment N5 (no GPU in CI).

Success criteria:
- the SE-margin gate rejects the three false claims (cherry-pick, dev-data,
  edited metric) and accepts the weak true 3-epoch gain;
- false-success control: the rerun-once check accepts the cherry-pick, so the
  fixture is hard enough to separate the two;
- margin sensitivity is pinned: with the per-seed (2 x sd) margin the true claim
  is rejected, so a later margin change shows as a failing test;
- a claimant seed list is refused before anything is read; results that do not
  cover exactly the gate's seeds are refused;
- every verdict says "preview" and carries its does-not-prove lines.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.certificates.replay import REQUIRED_FLAGS
from harness.rederive_gate import Gate, RefusedClaim, decide, main, rerun_once

FIX = json.loads((Path(__file__).with_name("fixtures") / "rederive_n5.json").read_text())
GATE = Gate(tuple(FIX["gate_seeds"]))
REC = {"weights_sha256": "w", "inputs_sha256": "i", "seed": 1729,
       "checkpoints": ["a" * 64, "b" * 64], "flags": {f: True for f in REQUIRED_FLAGS},
       "device": "gpu", "driver": "d"}


def _replay(ok):
    return {"claimed": REC, "replayed": REC} if ok else None


def _verdict(name, **kw):
    c = FIX["claims"][name]
    return decide(GATE, {"id": name}, FIX["baseline"], c["treated"], _replay(c["replay"]), **kw)


def test_se_gate_rejects_false_and_accepts_true():
    got = {n: _verdict(n)["verdict"] for n in FIX["claims"]}
    assert got == {"true_weak_3_epoch": "ACCEPT", "cherry_pick": "REJECT",
                   "dev_data": "REJECT", "edited_metric": "REJECT"}
    assert _verdict("edited_metric")["replay"] == "UNVERIFIABLE"


def test_control_rerun_once_accepts_the_cherry_pick():
    assert rerun_once(FIX["baseline"], FIX["claims"]["cherry_pick"]["rerun_once_value"])


def test_margin_sensitivity_per_seed_margin_rejects_the_true_claim():
    v = _verdict("true_weak_3_epoch", per_seed_margin=True)
    assert v["verdict"] == "REJECT"
    se = _verdict("true_weak_3_epoch")
    assert se["margin"] == pytest.approx(0.010493, abs=1e-5)
    assert se["mean_gain"] == pytest.approx(0.013707, abs=1e-5)


def test_claimant_seed_list_is_refused():
    with pytest.raises(RefusedClaim):
        decide(GATE, {"id": "x", "seeds": [1, 2]}, FIX["baseline"], FIX["baseline"], None)


def test_results_must_cover_exactly_the_gate_seeds():
    partial = dict(list(FIX["baseline"].items())[:4])
    with pytest.raises(RefusedClaim):
        decide(GATE, {"id": "x"}, FIX["baseline"], partial, _replay(True))


def test_replay_drift_rejects_a_real_gain():
    drift = dict(REC, checkpoints=["a" * 64, "c" * 64])
    v = decide(GATE, {"id": "t"}, FIX["baseline"], FIX["claims"]["true_weak_3_epoch"]["treated"],
               {"claimed": REC, "replayed": drift})
    assert v["verdict"] == "REJECT" and v["replay"] == "DRIFT"


def test_verdict_is_preview_with_limits():
    v = _verdict("true_weak_3_epoch")
    assert v["status"] == "preview" and len(v["does_not_prove"]) == 2


def test_cli_exit_codes(tmp_path, capsys):
    run = {"gate": {"seeds": FIX["gate_seeds"]}, "claim": {"id": "t"},
           "baseline": FIX["baseline"], "treated": FIX["claims"]["true_weak_3_epoch"]["treated"],
           "replay": _replay(True)}
    p = tmp_path / "run.json"
    p.write_text(json.dumps(run))
    assert main([str(p)]) == 0
    run["claim"]["seeds"] = [1]
    p.write_text(json.dumps(run))
    assert main([str(p)]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_flywheel_rederive_dispatches(tmp_path):
    from harness.cli_entry import main as flywheel
    run = {"gate": {"seeds": FIX["gate_seeds"]}, "claim": {"id": "c"},
           "baseline": FIX["baseline"], "treated": FIX["baseline"], "replay": _replay(True)}
    p = tmp_path / "run.json"
    p.write_text(json.dumps(run))
    assert flywheel(["rederive", str(p)]) == 1
