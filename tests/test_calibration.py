"""verifier calibration falsifier — a broken verifier must FAIL calibration.

The gate is only meaningful if it catches an untrustworthy oracle. So: a sound
oracle (PytestOracle) passes calibration (0 false accepts); a broken oracle
(always-pass) is CAUGHT (false accepts > 0 -> untrustworthy), and
require_calibrated refuses to proceed on it.
"""
from pathlib import Path

import pytest

from harness.oracle import PytestOracle, OracleResult
from harness.task import load_task
from harness.calibration import (
    CalibrationCase, calibrate, require_calibrated, UncalibratedOracleError,
    calibration_report)

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a - b\n"
NOOP = "def add(a, b):\n    return 0\n"

CASES = [
    CalibrationCase(CORRECT, should_pass=True, note="reference solution"),
    CalibrationCase(WRONG, should_pass=False, note="subtracts"),
    CalibrationCase(NOOP, should_pass=False, note="returns 0"),
]


class AlwaysPassOracle:
    oracle_type = "always-pass"
    def verify(self, candidate, task):
        return OracleResult(passed=True, cmd="noop", output_hash="x",
                            stdout_excerpt="", rc=0)


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_sound_oracle_is_trustworthy(task):
    r = calibrate(PytestOracle(), task, CASES)
    assert r.false_pos == 0, r.detail
    assert r.trustworthy is True
    assert r.true_pos == 1 and r.true_neg == 2
    assert "TRUSTWORTHY" in calibration_report(r)


def test_broken_oracle_is_caught(task):
    # the always-pass oracle accepts the two known-bad candidates -> 2 false
    # accepts -> untrustworthy. This is the load-bearing discrimination proof.
    r = calibrate(AlwaysPassOracle(), task, CASES)
    assert r.false_pos == 2
    assert r.trustworthy is False
    assert "UNTRUSTWORTHY" in calibration_report(r)


def test_require_calibrated_refuses_a_broken_oracle(task):
    require_calibrated(PytestOracle(), task, CASES)          # sound: no raise
    with pytest.raises(UncalibratedOracleError):
        require_calibrated(AlwaysPassOracle(), task, CASES)  # broken: raises


def test_receipt_is_deterministic(task):
    r1 = calibrate(PytestOracle(), task, CASES)
    r2 = calibrate(PytestOracle(), task, CASES)
    assert r1.receipt_hash == r2.receipt_hash
