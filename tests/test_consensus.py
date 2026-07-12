"""test_consensus.py — verifier ensembling and stability replay, re-checkably.

Success criteria:
  - each consensus rule (all / any / majority / weighted) decides correctly.
  - the receipt hash folds every member verdict and is stable across calls.
  - RepeatConsistencyOracle refuses a flaky pass, accepts a stable one.
  - construction guards reject empty members / bad rule / mismatched weights.
  - it composes with the integrity guard (a tampered consensus pass is refused).
"""
import pytest

from harness.consensus import ConsensusOracle, RepeatConsistencyOracle
from harness.integrity import GuardedOracle
from harness.oracle import OracleResult, StubOracle
from harness.task import Task


def _task():
    return Task(task_id="t", prompt="p", oracle="stub",
                oracle_cmd="pytest", workdir=".", candidate_path="s.py")


CLEAN = "def add(a, b):\n    return a + b\n"


def test_all_rule_requires_every_member():
    assert ConsensusOracle([StubOracle(True), StubOracle(True)]).verify(CLEAN, _task()).passed
    assert not ConsensusOracle([StubOracle(True), StubOracle(False)]).verify(CLEAN, _task()).passed


def test_any_and_majority_rules():
    assert ConsensusOracle([StubOracle(False), StubOracle(True)], rule="any").verify(CLEAN, _task()).passed
    maj = ConsensusOracle([StubOracle(True), StubOracle(True), StubOracle(False)], rule="majority")
    assert maj.verify(CLEAN, _task()).passed
    minority = ConsensusOracle([StubOracle(True), StubOracle(False), StubOracle(False)], rule="majority")
    assert not minority.verify(CLEAN, _task()).passed


def test_weighted_rule_respects_weights_and_threshold():
    # a heavy passing member (w=2) vs a light failing one (w=1): score 2/3
    members = [StubOracle(True), StubOracle(False)]
    assert ConsensusOracle(members, rule="weighted", weights=[2, 1], threshold=0.5).verify(CLEAN, _task()).passed
    assert not ConsensusOracle(members, rule="weighted", weights=[2, 1], threshold=0.7).verify(CLEAN, _task()).passed


def test_receipt_hash_folds_member_verdicts_and_is_stable():
    a = ConsensusOracle([StubOracle(True), StubOracle(True)])
    b = ConsensusOracle([StubOracle(True), StubOracle(False)])
    r1 = a.verify(CLEAN, _task())
    r2 = a.verify(CLEAN, _task())
    assert r1.output_hash == r2.output_hash                      # re-checkable, stable
    assert r1.output_hash != b.verify(CLEAN, _task()).output_hash  # different verdicts -> different hash


def test_construction_guards():
    with pytest.raises(ValueError):
        ConsensusOracle([])
    with pytest.raises(ValueError):
        ConsensusOracle([StubOracle(True)], rule="nope")
    with pytest.raises(ValueError):
        ConsensusOracle([StubOracle(True)], rule="weighted", weights=[1, 2])


class _FlakyOracle:
    """Passes every run but reports a different canonical output each time."""
    oracle_type = "flaky"

    def __init__(self):
        self._n = 0

    def verify(self, candidate, task):
        self._n += 1
        return OracleResult(passed=True, cmd="flaky",
                            output_hash=f"h{self._n}", stdout_excerpt="", rc=0)


def test_repeat_consistency_refuses_flaky_pass():
    res = RepeatConsistencyOracle(_FlakyOracle(), runs=3).verify(CLEAN, _task())
    assert res.passed is False
    assert "nondeterministic" in res.stdout_excerpt


def test_repeat_consistency_accepts_stable_pass():
    # StubOracle returns the same output_hash every call -> stable
    assert RepeatConsistencyOracle(StubOracle(True), runs=3).verify(CLEAN, _task()).passed


def test_repeat_needs_at_least_two_runs():
    with pytest.raises(ValueError):
        RepeatConsistencyOracle(StubOracle(True), runs=1)


def test_consensus_composes_with_integrity_guard():
    # both members "pass", but the candidate tampers with the check -> refused
    guarded = GuardedOracle(ConsensusOracle([StubOracle(True), StubOracle(True)]))
    res = guarded.verify("import pytest\npytest.skip('x')\n", _task())
    assert res.passed is False and "[integrity]" in res.stdout_excerpt
