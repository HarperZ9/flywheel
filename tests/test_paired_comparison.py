"""B4: the cluster guard between bench attempts and a pooled McNemar p.

The tests that matter are the two acceptance fixtures from the design of
record: 4 tasks x 3 correlated reps must yield per-task rows and a refusal
with reason cluster_correlated_reps and no pooled p; a task-level fixture
with at least 5 tasks must yield the exact p plus its MDE. Reference values
are hand-checked in comments.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.paired_comparison import (                              # noqa: E402
    MIN_TASK_CLUSTERS, SCHEMA, paired_comparison)


def _arm(name, rows):
    return {"arm": name, "attempts": [
        {"task_id": t, "repetition": r, "passed": p} for t, r, p in rows]}


def _replicated_fixture():
    """4 tasks x 3 reps. Hand-built truth table per task:

    t1: a passes all, b fails all           -> a_only 3, discordant 3
    t2: a passes r0,r1; b passes r0 only    -> a_only 1, discordant 1
    t3: both pass all                       -> discordant 0
    t4: a fails all, b passes r1 only       -> b_only 1, discordant 1
    """
    a = _arm("bare", [
        ("t1", 0, True), ("t1", 1, True), ("t1", 2, True),
        ("t2", 0, True), ("t2", 1, True), ("t2", 2, False),
        ("t3", 0, True), ("t3", 1, True), ("t3", 2, True),
        ("t4", 0, False), ("t4", 1, False), ("t4", 2, False)])
    b = _arm("governed", [
        ("t1", 0, False), ("t1", 1, False), ("t1", 2, False),
        ("t2", 0, True), ("t2", 1, False), ("t2", 2, False),
        ("t3", 0, True), ("t3", 1, True), ("t3", 2, True),
        ("t4", 0, False), ("t4", 1, True), ("t4", 2, False)])
    return a, b


# --- the acceptance fixture: correlated reps refuse the pooled p ------------

def test_correlated_reps_refuse_pooled_p_and_emit_per_task_rows():
    out = paired_comparison(*_replicated_fixture())
    assert out["schema"] == SCHEMA
    assert out["n_tasks"] == 4 and out["n_attempt_pairs"] == 12
    assert out["pooled"] is None
    assert out["pooled_refused"]["reason"] == "cluster_correlated_reps"
    rows = {r["task_id"]: r for r in out["per_task"]}
    assert len(rows) == 4
    assert rows["t1"] == {"task_id": "t1", "n_reps": 3, "a_passes": 3,
                          "b_passes": 0, "a_only": 3, "b_only": 0,
                          "discordant": 3, "concordant": 0}
    assert rows["t2"]["a_only"] == 1 and rows["t2"]["discordant"] == 1
    assert rows["t3"]["discordant"] == 0 and rows["t3"]["concordant"] == 3
    assert rows["t4"] == {"task_id": "t4", "n_reps": 3, "a_passes": 0,
                          "b_passes": 1, "a_only": 0, "b_only": 1,
                          "discordant": 1, "concordant": 2}


def test_no_p_value_leaks_into_the_refused_result():
    out = paired_comparison(*_replicated_fixture())
    assert "p_exact" not in str(sorted(_walk_keys(out)))


def _walk_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_keys(v)


# --- the acceptance fixture: genuine task-level pairs get p + MDE -----------

def test_task_level_pairs_yield_exact_p_and_mde():
    """6 tasks, 1 rep each. a passes t1-t5, b passes t1-t2 only; t6 both
    fail. So a_only = {t3,t4,t5} = 3, b_only = 0, m = 3, and the exact
    two-sided p is min(1, 2*C(3,0)/2^3) = 0.25. chi2_cc = (3-1)^2/3."""
    a = _arm("bare", [(f"t{i}", 0, i <= 5) for i in range(1, 7)])
    b = _arm("governed", [(f"t{i}", 0, i <= 2) for i in range(1, 7)])
    out = paired_comparison(a, b)
    assert "pooled_refused" not in out
    pooled = out["pooled"]
    assert pooled["unit"] == "task"
    assert pooled["b"] == 3 and pooled["c"] == 0 and pooled["discordant"] == 3
    assert pooled["p_exact"] == pytest.approx(0.25)
    assert pooled["chi2_cc"] == pytest.approx(4 / 3)
    mde = pooled["mde"]
    assert mde["n_pairs"] == 6 and mde["n_discordant"] == 3
    # 3 discordant pairs cannot reach alpha=0.05 at any split (best is 0.25),
    # and the MDE says so instead of inventing a detectable effect.
    assert mde["detectable"] is None and "NO SPLIT" in mde["note"]


def test_fully_discordant_eight_tasks_reach_significance():
    """8 tasks, all discordant toward a: p = 2*C(8,0)/2^8 = 0.0078125, and
    the smallest callable imbalance is all 8, i.e. mde_delta = 1.0."""
    a = _arm("bare", [(f"t{i}", 0, True) for i in range(8)])
    b = _arm("governed", [(f"t{i}", 0, False) for i in range(8)])
    pooled = paired_comparison(a, b)["pooled"]
    assert pooled["p_exact"] == pytest.approx(0.0078125)
    assert pooled["mde"]["detectable"] == 8
    assert pooled["mde"]["mde_delta"] == pytest.approx(1.0)


# --- refusals ---------------------------------------------------------------

def test_unequal_task_sets_refuse_the_whole_comparison():
    a = _arm("bare", [("t1", 0, True), ("t2", 0, True)])
    b = _arm("governed", [("t1", 0, True), ("t3", 0, False)])
    out = paired_comparison(a, b)
    assert out["refused"]["reason"] == "unequal_task_sets"
    assert out["refused"]["a_only_tasks"] == ["t2"]
    assert out["refused"]["b_only_tasks"] == ["t3"]
    assert "per_task" not in out and "pooled" not in out


def test_unequal_repetition_sets_refuse_the_whole_comparison():
    a = _arm("bare", [("t1", 0, True), ("t1", 1, True)])
    b = _arm("governed", [("t1", 0, True), ("t1", 2, True)])
    out = paired_comparison(a, b)
    assert out["refused"]["reason"] == "unequal_repetition_sets"


def test_fewer_than_five_task_clusters_refuse_the_pooled_p():
    a = _arm("bare", [(f"t{i}", 0, True) for i in range(4)])
    b = _arm("governed", [(f"t{i}", 0, False) for i in range(4)])
    out = paired_comparison(a, b)
    assert out["pooled"] is None
    assert out["pooled_refused"]["reason"] == "cluster_count_below_minimum"
    assert str(MIN_TASK_CLUSTERS) in out["pooled_refused"]["detail"]
    assert len(out["per_task"]) == 4


def test_malformed_attempts_raise_rather_than_guess():
    good = _arm("governed", [("t1", 0, True)])
    with pytest.raises(ValueError):
        paired_comparison({"arm": "bare", "attempts": [
            {"task_id": "t1", "repetition": 0, "passed": "yes"}]}, good)
    with pytest.raises(ValueError):
        paired_comparison({"arm": "bare", "attempts": [
            {"task_id": "t1", "repetition": 0, "passed": True},
            {"task_id": "t1", "repetition": 0, "passed": False}]}, good)
    with pytest.raises(ValueError):
        paired_comparison({"arm": "", "attempts": [
            {"task_id": "t1", "repetition": 0, "passed": True}]}, good)
