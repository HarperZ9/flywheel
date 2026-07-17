"""Sealed forecasts from measured outcome vectors: the uplift artifact's
censored per-task records (outcome + attempts) reconstruct exact candidate
sequences; the Jeffreys per-task model forecasts a FRESH best-of-k run and
seals the forecast content-addressed BEFORE any such run exists, with the
iid pooled baseline pre-registered beside it so adjudication is a
comparison, not a choice."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from passn_model import forecast_fresh_run, vectors_from_uplift

UPLIFT_DOC = {
    "comparison_key": "uplift:test",
    "rows": [
        {"arm": "bare", "provider": "p", "tasks": [
            {"task_id": "a", "outcome": "pass", "attempts": 1}]},
        {"arm": "wrapped", "provider": "p", "n_candidates": 3, "tasks": [
            {"task_id": "easy", "outcome": "pass", "attempts": 1},
            {"task_id": "late", "outcome": "pass", "attempts": 3},
            {"task_id": "never", "outcome": "fail", "attempts": 3},
        ]},
    ],
}


def test_unverifiable_tasks_are_dropped_not_recoded_as_failures():
    # The uplift bench excludes a task its oracle refused to dispose; the
    # forecast must do the same, never seal it as m fabricated failures.
    doc = {"rows": [{"arm": "wrapped", "tasks": [
        {"task_id": "refused", "outcome": "unverifiable", "attempts": 3},
        {"task_id": "real", "outcome": "fail", "attempts": 2},
    ]}]}
    rows = vectors_from_uplift(doc)
    ids = {r["task_id"] for r in rows}
    assert "refused" not in ids
    assert "real" in ids


def test_censored_reconstruction_is_exact():
    rows = vectors_from_uplift(UPLIFT_DOC)
    by = {r["task_id"]: r for r in rows}
    # pass at attempt 1: one draw, one success
    assert by["easy"] == {"task_id": "easy", "n": 1, "c": 1}
    # pass at attempt 3: two real failures then one success
    assert by["late"] == {"task_id": "late", "n": 3, "c": 1}
    # fail after 3: three real failures
    assert by["never"] == {"task_id": "never", "n": 3, "c": 0}
    # only the wrapped arm's sampling policy is used
    assert "a" not in by


def test_forecast_shape_and_ordering():
    rows = vectors_from_uplift(UPLIFT_DOC)
    f = forecast_fresh_run(rows, k=5)
    assert f["schema"] == "flywheel.passk-forecast/v1"
    assert 0.0 <= f["expected_pass_rate"] <= 1.0
    lo, hi = f["interval_95"]
    assert 0.0 <= lo <= f["expected_pass_rate"] <= hi <= 1.0
    per = {t["task_id"]: t["q"] for t in f["per_task"]}
    # a task that passed first try forecasts higher than one that never did
    assert per["easy"] > per["never"]
    # Jeffreys keeps the never-passer alive but below a coin flip
    assert 0.0 < per["never"] < 0.5
    # the iid baseline is pre-registered inside the same sealed artifact
    assert 0.0 <= f["iid_baseline"]["expected_pass_rate"] <= 1.0
    assert f["iid_baseline"]["pooled_p"] == pytest.approx(2 / 7)


def test_seal_is_content_addressed_and_stable():
    rows = vectors_from_uplift(UPLIFT_DOC)
    f1 = forecast_fresh_run(rows, k=5, source="artifact-x")
    f2 = forecast_fresh_run(rows, k=5, source="artifact-x")
    assert f1["seal"] == f2["seal"] and len(f1["seal"]) == 64
    f3 = forecast_fresh_run(rows, k=4, source="artifact-x")
    assert f3["seal"] != f1["seal"], "a different forecast must reseal"
