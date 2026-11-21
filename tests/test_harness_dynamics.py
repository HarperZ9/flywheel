"""Tests for harness.harness_dynamics."""

from __future__ import annotations

from harness.harness_dynamics import (
    ExperimentCandidate,
    center_and_clip_scores,
    evaluate_maintainability_debt,
    lyapunov_trajectory_stability,
    select_highest_ig_experiment,
)


def test_maintainability_debt_gate_accepts_clean_and_rejects_rlvr_bloat() -> None:
    clean = {
        "mod.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "test_mod.py": "def test_add():\n    assert 2 + 2 == 4\n",
    }
    ok = evaluate_maintainability_debt(clean)
    assert ok["verdict"] == "ACCEPT"
    assert ok["violation_count"] == 0

    bloated = {
        "noisy.py": "\n".join(["# redundant comment"] * 12 + ["x = 1", "y = 2"]),
        "test_fake.py": "def test_nothing():\n    assert True\n",
    }
    bad = evaluate_maintainability_debt(bloated)
    assert bad["verdict"] == "REJECT"
    rules = {v["rule"] for v in bad["violations"]}
    assert {"comment_bloat", "trivial_test"} <= rules


def test_strong_inference_selector_prefers_fast_decisive_split_over_slow_sweep() -> None:
    priors = [0.25, 0.25, 0.25, 0.25]
    # Fast binary split: cuts 4 hypotheses cleanly in half in 1 second -> 1.0 bit/s.
    fast_split = ExperimentCandidate(
        experiment_id="fast-binary-split",
        cost_seconds=1.0,
        outcome_likelihoods=((1.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 1.0)),
    )
    # Slow full sweep: resolves all 2.0 bits, but costs 10 seconds -> 0.2 bit/s.
    slow_full = ExperimentCandidate(
        experiment_id="slow-full-sweep",
        cost_seconds=10.0,
        outcome_likelihoods=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    res = select_highest_ig_experiment(priors, [slow_full, fast_split])
    assert res["selected"] == "fast-binary-split"
    assert res["ranking"][0]["ig_bits_per_second"] == 1.0
    assert res["ranking"][1]["ig_bits_per_second"] == 0.2


def test_lyapunov_stability_and_isometric_score_centering() -> None:
    stable = lyapunov_trajectory_stability([1.0, 0.5, 0.25, 0.125])
    assert stable["regime"] == "SELF_STABILIZING"
    assert stable["lyapunov_exponent"] < 0

    diverging = lyapunov_trajectory_stability([0.1, 0.2, 0.4, 0.8])
    assert diverging["regime"] == "DIVERGING"
    assert diverging["lyapunov_exponent"] > 0

    centered = center_and_clip_scores([10.0, 12.0, 14.0, 16.0], max_norm=1.0)
    assert centered["clipped"] is True
    assert abs(sum(centered["advantages"])) < 1e-4
    l2 = sum(x * x for x in centered["advantages"]) ** 0.5
    assert abs(l2 - 1.0) < 1e-4
