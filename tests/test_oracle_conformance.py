"""Oracle determinism contract (HARNESS.md §proof-envelope invariant).

Every Oracle subclass MUST produce a stable output_hash when verify() runs
twice on the same candidate + task in FRESH workdirs. This is the root
prevention of the M1 bug class (non-deterministic pytest timing broke the
receipt chain). The M1 falsifier caught the bug once, historically; this
contract prevents the bug CLASS for every future oracle.

Depth-2 capability artifact: M2 adds SeedOracle / SandboxedOracle to ORACLES
and they must pass or the receipt chain is broken at the source.
"""
from pathlib import Path

import pytest

from harness.oracle import PytestOracle, StubOracle
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"

ORACLES = ["pytest", "stub-pass", "stub-fail"]


def _make_oracle(kind):
    if kind == "pytest":
        return PytestOracle()
    if kind == "stub-pass":
        return StubOracle(True)
    if kind == "stub-fail":
        return StubOracle(False)
    raise ValueError(kind)


@pytest.mark.parametrize("kind", ORACLES)
def test_oracle_hash_is_deterministic_across_runs(kind, tmp_path):
    oracle = _make_oracle(kind)
    t1 = load_task(TASK_DIR, workdir=tmp_path / "w1")
    r1 = oracle.verify(CORRECT, t1)
    t2 = load_task(TASK_DIR, workdir=tmp_path / "w2")
    r2 = oracle.verify(CORRECT, t2)
    assert r1.output_hash == r2.output_hash, (
        f"{kind}: non-deterministic oracle output — receipt chain would break. "
        f"run1={r1.output_hash} run2={r2.output_hash}")
    assert r1.passed == r2.passed
