"""failure-corpus falsifier — rejections become durable regression guards.

Properties:
  1. record/load round-trips and dedups by candidate_hash.
  2. record_if_rejected banks ONLY real rejections (a passing candidate isn't a
     failure).
  3. replay against the sound oracle is clean (all known-bads still rejected);
     against a WEAKENED oracle it surfaces regressions (now-accepted known-bads).
  4. the corpus feeds calibration (to_calibration_cases -> calibrate).
"""
from pathlib import Path

import pytest

from harness.oracle import PytestOracle, OracleResult
from harness.task import load_task
from harness.failure_corpus import (
    FailureCase, record, load, record_if_rejected, to_calibration_cases, replay)
from harness.calibration import calibrate

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a - b\n"
NOOP = "def add(a, b):\n    return 0\n"


class AlwaysPassOracle:
    oracle_type = "always-pass"
    def verify(self, candidate, task):
        return OracleResult(passed=True, cmd="noop", output_hash="x", stdout_excerpt="", rc=0)


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_record_load_dedup(tmp_path, task):
    store = tmp_path / "fail.jsonl"
    c = FailureCase(task_id="example_pass", candidate=WRONG, oracle_type="pytest",
                    oracle_input_hash="h")
    assert record(store, c) is True
    assert record(store, c) is False              # dedup
    loaded = load(store)
    assert len(loaded) == 1 and loaded[0].candidate == WRONG


def test_record_if_rejected_only_banks_failures(tmp_path, task):
    store = tmp_path / "fail.jsonl"
    assert record_if_rejected(store, task, WRONG, PytestOracle()) is True   # rejected -> banked
    assert record_if_rejected(store, task, CORRECT, PytestOracle()) is False  # passes -> not a failure
    assert len(load(store)) == 1


def test_replay_clean_on_sound_oracle_regresses_on_weakened(tmp_path, task):
    store = tmp_path / "fail.jsonl"
    record_if_rejected(store, task, WRONG, PytestOracle())
    record_if_rejected(store, task, NOOP, PytestOracle())
    failures = load(store)
    assert len(failures) == 2
    # sound oracle: every known-bad still rejected
    assert replay(PytestOracle(), task, failures)["clean"] is True
    # weakened oracle: now accepts the known-bads -> regressions surfaced
    r = replay(AlwaysPassOracle(), task, failures)
    assert r["clean"] is False and len(r["regressions"]) == 2


def test_corpus_feeds_calibration(tmp_path, task):
    store = tmp_path / "fail.jsonl"
    record_if_rejected(store, task, WRONG, PytestOracle())
    cases = to_calibration_cases(load(store))
    assert cases and all(c.should_pass is False for c in cases)
    # a sound oracle rejects all banked known-bads -> 0 false accepts
    r = calibrate(PytestOracle(), task, cases)
    assert r.false_pos == 0 and r.true_neg == len(cases)
