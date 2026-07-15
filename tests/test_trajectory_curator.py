"""Falsifiers for trajectory_curator.py — the six-gate admission + honest ceiling.

Load-bearing: (1) a genuine witnessed, independently-graded row clears all six
gates once its graders carry refusal evidence; (2) a self-graded row is rejected
(independence); (3) a duplicate is rejected and the recirculation ceiling is
1/(1-r), admitted never exceeds novel submissions; (4) a grade that cannot fail
verifies nothing: no flippable input, a rubber-stamp grader with no recorded
refusal, and a grade input unbacked by the hash chain are all rejected.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from harness.trajectory_curator import curate_trajectories, screen_trajectory

_FIXTURE = Path(__file__).parent / "fixtures_forum_gradable_pinned.json"


def _row():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _refuting_row():
    """A distinct row whose graders both refused: recorded ok=false counter-
    examples, reward re-derived honestly (0/2), label FAIL. Still witnessed:
    admission is about gradability, not success."""
    row = _row()
    row["task_id"] = "eeeeeeeeeeeeeeee"
    row["prompt"] = "sum a list of integers"
    for g in row["oracle"]["grade_inputs"]:
        g["ok"] = False
    row["grade"]["reward"] = 0.0
    row["grade"]["label"] = "FAIL"
    row["grade"]["refuted"] = 2
    return row


def test_rubber_stamp_grader_rejected_standalone():
    # The pinned row is all ok=true from graders never seen to refuse anything.
    # A verifier that cannot fail verifies nothing: without refusal evidence
    # the load-bearing gate must refuse it, not admit it on flip arithmetic.
    r = screen_trajectory(_row())
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")
    assert "refus" in r["gates"]["oracle_can_fail"].lower()


def test_genuine_row_clears_every_gate_with_refusal_witness():
    r = screen_trajectory(_row(), grader_refusals={"validator", "verifier"})
    assert r["admitted"], r["gates"]
    assert all(v == "PASS" for v in r["gates"].values()), r["gates"]


def test_partial_refusal_witness_still_rejected():
    # One rubber-stamp grader taints the row: EVERY counted grader needs a
    # recorded refusal, or its checks are not evidence.
    r = screen_trajectory(_row(), grader_refusals={"validator"})
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")


def test_in_batch_refusals_witness_an_all_pass_row():
    # A batch carrying its own counter-examples: the refuting row demonstrates
    # both graders CAN emit ok=false, which witnesses the all-pass row.
    out = curate_trajectories([_refuting_row(), _row()])
    assert out["admitted"] == 2, out["rejected_rows"]
    assert set(out["grader_refusals_witnessed"]) == {"validator", "verifier"}


def test_unbacked_grade_input_rejected():
    # A grade input with no matching hash-chained entry (actor+kind) is a
    # fabricated check: reward still re-derives, so flip arithmetic passes,
    # but the chain does not back it. Its ok=false must also NOT count as
    # refusal evidence for itself.
    row = _row()
    row["oracle"]["grade_inputs"].append({"actor": "ghost", "kind": "verdict", "ok": False})
    row["grade"]["reward"] = round(2 / 3, 6)
    row["grade"]["label"] = "FAIL"
    row["grade"]["refuted"] = 1
    row["grade"]["checks"] = 3
    row["grade"]["graders"] = ["validator", "verifier", "ghost"]
    r = screen_trajectory(row, grader_refusals={"validator", "verifier", "ghost"})
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")
    assert "chain" in r["gates"]["oracle_can_fail"].lower()


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
    out = curate_trajectories([row, dup], grader_refusals={"validator", "verifier"})
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
    out = curate_trajectories([row, other], grader_refusals={"validator", "verifier"})
    assert out["admitted"] == 2
    assert out["reuse_fraction"] == 0.0
    assert out["amortization_ceiling"] == 1.0
