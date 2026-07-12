"""test_hard_lane_seed.py — the seed hard lane runs end to end.

Success criteria:
  - the seed manifest loads; every task is FRESH vs an older cutoff and licensed.
  - the held-out accept tier accepts a correct solution and REJECTS a gamed one
    that only handles the visible cases.
"""
import shutil
from pathlib import Path

from harness.consensus import accept_gate
from harness.hard_lane import VERDICT_FRESH, admit, load_lane
from harness.task import Task

LANE = Path(__file__).resolve().parent.parent / "tasks" / "hard-lane"

_CORRECT = (
    "def merge_intervals(intervals):\n"
    "    out = []\n"
    "    for s, e in sorted(intervals, key=lambda p: p[0]):\n"
    "        if out and s <= out[-1][1]:\n"
    "            out[-1][1] = max(out[-1][1], e)\n"
    "        else:\n"
    "            out.append([s, e])\n"
    "    return out\n")

_GAMED = (                                    # no sort: passes the (sorted) visible cases only
    "def merge_intervals(intervals):\n"
    "    out = []\n"
    "    for s, e in intervals:\n"
    "        if out and s <= out[-1][1]:\n"
    "            out[-1][1] = max(out[-1][1], e)\n"
    "        else:\n"
    "            out.append([s, e])\n"
    "    return out\n")


def test_seed_lane_loads_all_fresh_and_licensed():
    lane = load_lane(LANE / "seed.jsonl")
    assert len(lane) == 3
    rep = admit(lane, "2025-06-01")           # all authored 2026-07 -> after the cutoff
    assert rep["counts"][VERDICT_FRESH] == 3 and rep["unlicensed"] == []


def _merge_task(tmp_path):
    dst = tmp_path / "merge-intervals"
    shutil.copytree(LANE / "merge-intervals", dst)
    return Task(task_id="merge-intervals", prompt="merge overlapping intervals",
                oracle="pytest", oracle_cmd="python -m pytest visible_tests.py",
                held_out_cmd="python -m pytest hidden_tests.py",
                workdir=str(dst), candidate_path="sol.py")


def test_correct_solution_accepted(tmp_path):
    task = _merge_task(tmp_path)
    assert accept_gate(task, timeout=60).verify(_CORRECT, task).passed is True


def test_gamed_solution_rejected_by_held_out(tmp_path):
    task = _merge_task(tmp_path)
    assert accept_gate(task, timeout=60).verify(_GAMED, task).passed is False
