"""M7 scorecard persistence falsifier (F8) — reconstruct without re-running.

A scorecard round-trips, declares its metric semantics, and supports delta-vs-a-
pinned-baseline so a later run is compared without re-executing the baseline.
"""
from harness.eval import (EvalReport, scorecard, save_scorecard, load_scorecard,
                          delta_vs_pinned, METRICS)


def _reports(pass_rate):
    return {
        "single_shot": EvalReport("single_shot", 8, 0.5, 1.0, 1.0, 1.0),
        "verified_inference": EvalReport("verified_inference", 8, pass_rate, 4.0, 4.0, 1.0),
    }


def test_scorecard_declares_metrics_and_arms():
    sc = scorecard(_reports(0.75), meta={"model_ref": "x"})
    assert sc["metrics"] == METRICS
    assert sc["arms"]["verified_inference"]["pass_rate"] == 0.75
    assert sc["meta"]["model_ref"] == "x"


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "sc.json"
    save_scorecard(p, _reports(0.75), meta={"commit": "abc"})
    sc = load_scorecard(p)
    assert sc["arms"]["verified_inference"]["pass_rate"] == 0.75
    assert sc["meta"]["commit"] == "abc"


def test_delta_vs_pinned_detects_direction(tmp_path):
    pinned = scorecard(_reports(0.60))
    assert delta_vs_pinned(_reports(0.75), pinned)["verdict"] == "IMPROVED"
    assert delta_vs_pinned(_reports(0.50), pinned)["verdict"] == "REGRESSED"
    assert delta_vs_pinned(_reports(0.60), pinned)["verdict"] == "FLAT"
    d = delta_vs_pinned(_reports(0.75), pinned)
    assert abs(d["pass_rate_delta"] - 0.15) < 1e-9
