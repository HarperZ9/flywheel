"""Falsifiers for the scorecard confidence-interval tool.

Load-bearing properties:
  - Wilson interval matches hand-checked reference values.
  - The 9/10 vs 8/10 hard-set difference carries an interval that INCLUDES
    zero (the "inside noise" statement is quantified, not asserted).
  - Paired bootstrap is used when per_task vectors exist, and is deterministic
    under the fixed seed.
  - A large-N separation DOES exclude zero (the tool can say yes, not only no).
  - eval.scorecard round-trips per_task so future runs feed the paired path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_benchmark_ci import (wilson_interval, newcombe_diff_interval,
                                      paired_bootstrap_diff, analyze)
from harness.eval import EvalReport, scorecard


def test_wilson_reference_values():
    lo, hi = wilson_interval(8, 10)
    assert abs(lo - 0.4902) < 0.01 and abs(hi - 0.9433) < 0.01
    lo, hi = wilson_interval(9, 10)
    assert abs(lo - 0.5958) < 0.01 and abs(hi - 0.9821) < 0.01
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_hard_set_difference_includes_zero():
    lo, hi = newcombe_diff_interval(9, 10, 8, 10)
    assert lo < 0.0 < hi, "9/10 vs 8/10 must not exclude zero at n=10"


def test_large_n_separation_excludes_zero():
    lo, hi = newcombe_diff_interval(90, 100, 60, 100)
    assert lo > 0.0, "a 30-point gap at n=100 should exclude zero"


def test_paired_bootstrap_deterministic_and_sane():
    cand = [True] * 9 + [False]
    base = [True] * 8 + [False] * 2
    a = paired_bootstrap_diff(cand, base)
    b = paired_bootstrap_diff(cand, base)
    assert a == b, "fixed seed must make the bootstrap reproducible"
    assert a[0] <= 0.1 <= a[1]


def test_analyze_prefers_paired_when_vectors_exist():
    card = {"arms": {
        "verified_inference": {"n_tasks": 10, "pass_rate": 0.9,
                               "per_task": [{"task_id": f"t{i}", "passed": i != 9}
                                            for i in range(10)]},
        "single_shot": {"n_tasks": 10, "pass_rate": 0.8,
                        "per_task": [{"task_id": f"t{i}", "passed": i < 8}
                                     for i in range(10)]},
    }}
    result = analyze(card)
    assert result["difference"]["method"] == "paired_bootstrap_10000"
    assert result["difference"]["includes_zero"] is True


def test_analyze_falls_back_to_newcombe_without_vectors():
    card = {"arms": {
        "verified_inference": {"n_tasks": 10, "pass_rate": 0.9},
        "single_shot": {"n_tasks": 10, "pass_rate": 0.8},
    }}
    result = analyze(card)
    assert result["difference"]["method"] == "newcombe_unpaired_approximation"
    assert result["difference"]["includes_zero"] is True


def test_scorecard_roundtrips_per_task():
    rep = EvalReport("single_shot", 2, 0.5, 1.0, 1.0, 1.0,
                     per_task=[{"task_id": "a", "passed": True, "oracle_calls": 1},
                               {"task_id": "b", "passed": False, "oracle_calls": 1}])
    card = scorecard({"single_shot": rep})
    assert card["arms"]["single_shot"]["per_task"][0]["task_id"] == "a"
    # arms without per_task stay schema-compatible (no empty key emitted)
    bare = scorecard({"single_shot": EvalReport("single_shot", 0, 0.0, 0.0, 0.0, 0.0)})
    assert "per_task" not in bare["arms"]["single_shot"]
