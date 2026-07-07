"""Falsifiers for trajectory_curator.py — the six-gate admission + honest ceiling.

Load-bearing: (1) a genuine witnessed, independently-graded row clears all six
gates; (2) a self-graded row is rejected (independence); (3) a duplicate is
rejected and the recirculation ceiling is 1/(1-r), admitted never exceeds novel
submissions; (4) a grade that cannot fail (no flippable input) is rejected.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from harness.trajectory_curator import curate_trajectories, screen_trajectory

_FIXTURE = Path(__file__).parent / "fixtures_forum_gradable_pinned.json"


def _row():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_genuine_row_clears_every_gate():
    r = screen_trajectory(_row())
    assert r["admitted"], r["gates"]
    assert all(v == "PASS" for v in r["gates"].values()), r["gates"]


def test_self_graded_rejected():
    row = _row()
    row["grade"]["graders"] = ["worker"]  # worker is also a producer -> not independent
    r = screen_trajectory(row)
    assert not r["admitted"]
    assert r["gates"]["grade_independent"].startswith("FAIL")


def test_answer_leaked_into_prompt_rejected():
    row = _row()
    row["prompt"] = "please output exactly: sorted"   # answer 'sorted' now verbatim in prompt
    r = screen_trajectory(row)
    assert not r["admitted"]
    assert r["gates"]["grade_independent"].startswith("FAIL")


def test_vacuous_grade_rejected():
    # a run nobody independently checked: no grade inputs -> cannot fail, no coverage
    row = _row()
    row["oracle"]["grade_inputs"] = []
    row["grade"] = {"reward": 0.0, "label": "UNVERIFIABLE", "checks": 0,
                    "refuted": 0, "producers": ["worker"], "graders": [],
                    "derivation": row["grade"]["derivation"]}
    r = screen_trajectory(row)
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")
    assert r["gates"]["min_coverage"].startswith("FAIL")


def test_duplicate_rejected_and_honest_ceiling():
    row = _row()
    dup = copy.deepcopy(row)  # identical prompt + answer
    out = curate_trajectories([row, dup])
    assert out["admitted"] == 1          # only the novel one
    assert out["rejected"] == 1
    assert out["reuse_fraction"] == 0.5
    assert out["amortization_ceiling"] == 2.0   # 1/(1-0.5)
    # admitted never exceeds the novel (non-duplicate) submission count
    novel = out["submitted"] - out["rejected"]
    assert out["admitted"] <= novel


def test_batch_of_distinct_rows_all_admitted():
    row = _row()
    other = copy.deepcopy(row)
    other["task_id"] = "ffffffffffffffff"
    other["prompt"] = "reverse a string"
    other["trajectory"]["answer"] = "reversed"
    out = curate_trajectories([row, other])
    assert out["admitted"] == 2
    assert out["reuse_fraction"] == 0.0
    assert out["amortization_ceiling"] == 1.0
