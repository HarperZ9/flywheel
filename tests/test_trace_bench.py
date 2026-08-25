"""Trace-to-bench: the improvement loop with receipts.

Every stored agent run -- pass or fail -- is a benchmark task waiting to
happen: the run's goal is the prompt, the run's own test command is the
gate, and the recorded verdict is the prior outcome. Convert traces into
a task set, re-run it across any endpoints, and a regression is a
previously-passing task that now fails -- sealed, comparable, and
re-checkable offline. Prime Intellect closes this loop for RL training;
this closes it for verified evaluation on private traffic.
"""
import json

import pytest

from harness.trace_bench import (
    regression_report,
    traces_to_task_set,
    write_task_set,
)


def _run(run_id, goal, verdict, test_cmd="python -m pytest -q",
         endpoint="ox-alpha"):
    return {
        "run_id": run_id,
        "goal": goal,
        "verdict": verdict,
        "endpoint": endpoint,
        "test_cmd": test_cmd,
        "steps": [{"tool": "edit", "detail": "x"}],
    }


def test_traces_become_tasks_with_prior_outcomes(tmp_path):
    runs = [_run("aa11", "fix the login bug", "PASS"),
            _run("bb22", "add the export button", "FAIL")]
    path = traces_to_task_set(runs, out_path=tmp_path / "bench.jsonl")
    tasks = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines()]
    assert [t["task_id"] for t in tasks] == ["trace-aa11", "trace-bb22"]
    assert tasks[0]["prompt"] == "fix the login bug"
    assert tasks[0]["gate_cmd"] == "python -m pytest -q"
    assert tasks[0]["prior_verdict"] == "PASS"
    assert tasks[1]["prior_verdict"] == "FAIL"


def test_traces_without_a_test_cmd_are_skipped_not_faked(tmp_path):
    runs = [_run("aa11", "no gate recorded", "PASS", test_cmd="")]
    path = traces_to_task_set(runs, out_path=tmp_path / "bench.jsonl")
    tasks = path.read_text(encoding="utf-8").splitlines()
    assert tasks == [], (
        "a run with no gate command cannot be verified; it is never "
        "faked into the task set")


def test_dedup_keeps_the_newest_attempt(tmp_path):
    runs = [_run("aa11", "fix the bug", "PASS"),
            _run("aa11", "fix the bug (retry)", "FAIL")]
    path = traces_to_task_set(runs, out_path=tmp_path / "bench.jsonl")
    tasks = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines()]
    assert len(tasks) == 1
    assert tasks[0]["prompt"] == "fix the bug (retry)"


def test_write_then_load_round_trips_through_the_bench_loader(tmp_path):
    from harness.verified_bench import load_task_set
    runs = [_run("aa11", "fix the login bug", "PASS")]
    path = traces_to_task_set(runs, out_path=tmp_path / "bench.jsonl")
    tasks = load_task_set(path)
    assert tasks[0]["task_id"] == "trace-aa11"


def test_regression_report_flags_previously_passing_now_failing():
    prior = {"attempts": [
        {"task_id": "trace-aa11", "endpoint": "ox-alpha",
         "gate_pass": True},
        {"task_id": "trace-bb22", "endpoint": "ox-alpha",
         "gate_pass": False},
    ]}
    current = {"attempts": [
        {"task_id": "trace-aa11", "endpoint": "ox-alpha",
         "gate_pass": False},
        {"task_id": "trace-bb22", "endpoint": "ox-alpha",
         "gate_pass": True},
    ]}
    report = regression_report(prior, current)
    assert report["regressions"] == [
        {"task_id": "trace-aa11", "endpoint": "ox-alpha",
         "prior": "PASS", "current": "FAIL"}]
    assert report["improvements"] == [
        {"task_id": "trace-bb22", "endpoint": "ox-alpha",
         "prior": "FAIL", "current": "PASS"}]
    assert report["stable"] == 0
    assert report["does_not_prove"]


def test_regression_report_is_empty_for_identical_runs():
    attempts = [{"task_id": "t1", "endpoint": "e", "gate_pass": True}]
    report = regression_report({"attempts": attempts},
                               {"attempts": list(attempts)})
    assert report["regressions"] == []
    assert report["improvements"] == []
    assert report["stable"] == 1


def test_new_tasks_are_reported_not_silently_dropped():
    prior = {"attempts": []}
    current = {"attempts": [
        {"task_id": "trace-new", "endpoint": "e", "gate_pass": False}]}
    report = regression_report(prior, current)
    assert report["new"] == [{"task_id": "trace-new", "endpoint": "e",
                              "current": "FAIL"}]
