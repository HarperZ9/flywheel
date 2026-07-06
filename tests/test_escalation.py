"""M4 escalation falsifier (harness/escalation.py — cheap->expensive gating).

C2 invariant: cheap tiers PRUNE, only the terminal tier ACCEPTS. A candidate
that passes compile but fails test is NOT accepted (no dense-reward override).
Compute saving: a candidate that fails compile never reaches the expensive test
tier (fast-fail prune).
"""
from pathlib import Path

import pytest

from harness.escalation import CompileOracle, EscalationOracle
from harness.oracle import OracleResult, StubOracle
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
COMPILES_WRONG = "def add(a, b):\n    return a * b\n"
SYNTAX_ERROR = "def add(a, b)\n    return a + b\n"


class CountingOracle:
    """Wraps an oracle, counts verify() calls — to prove the expensive tier is
    skipped when a cheap tier prunes."""
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.oracle_type = getattr(inner, "oracle_type", "counting")

    def verify(self, candidate, task):
        self.calls += 1
        return self.inner.verify(candidate, task)


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_compile_pass_test_pass_is_accepted(task):
    esc = EscalationOracle([("compile", CompileOracle()),
                            ("test", StubOracle(True))])
    r = esc.verify(CORRECT, task)
    assert r.passed


def test_c2_compile_pass_test_fail_not_accepted(task):
    """The C2 invariant: cheap-tier pass does NOT override terminal fail."""
    esc = EscalationOracle([("compile", CompileOracle()),
                            ("test", StubOracle(False))])
    r = esc.verify(COMPILES_WRONG, task)
    assert not r.passed, "compile pass must not override terminal test fail"
    assert "[test]" in r.stdout_excerpt


def test_compile_fail_prunes_expensive_tier_not_run(task):
    """Compute saving: a non-compiling candidate fails the cheap tier and the
    expensive test tier is NEVER called."""
    test_oracle = CountingOracle(StubOracle(True))
    esc = EscalationOracle([("compile", CompileOracle()),
                            ("test", test_oracle)])
    r = esc.verify(SYNTAX_ERROR, task)
    assert not r.passed
    assert "[compile]" in r.stdout_excerpt
    assert test_oracle.calls == 0, "expensive tier must not run on a compile fail"


def test_compile_fail_fast_returns_compile_verdict(task):
    test_oracle = CountingOracle(StubOracle(True))
    esc = EscalationOracle([("compile", CompileOracle()),
                            ("test", test_oracle)])
    r = esc.verify(SYNTAX_ERROR, task)
    assert r.rc != 0
    assert "compile_fail" in r.output_hash


def test_single_terminal_tier_acts_as_plain_oracle(task):
    esc = EscalationOracle([("test", StubOracle(True))])
    assert esc.verify(CORRECT, task).passed
    esc2 = EscalationOracle([("test", StubOracle(False))])
    assert not esc2.verify(CORRECT, task).passed


def test_escalation_with_real_pytest_oracle(task):
    """End-to-end: compile tier + real pytest tier on the example task."""
    from harness.oracle import PytestOracle
    esc = EscalationOracle([("compile", CompileOracle()),
                            ("test", PytestOracle())])
    assert esc.verify(CORRECT, task).passed
    assert not esc.verify(COMPILES_WRONG, task).passed
    assert not esc.verify(SYNTAX_ERROR, task).passed
