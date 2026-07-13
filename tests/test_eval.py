"""M7 eval-framework falsifier (harness/eval.py — the publishable result).

The framework must produce HONEST outcomes both ways:
  1. Where the harness's best-of-N rescues a weak proposer (low pass@1), the
     verified_inference arm beats single_shot -> compare() == MATCH.
  2. Where the proposer is already strong (single_shot passes), the harness
     gains nothing artificial -> both pass equally.
  3. Receipt-reproducibility is 100% by construction (every accept re-checkable).
  4. Budget (oracle_calls) is tracked honestly.
The whole-program falsifier: compare() can return DRIFT (single_shot wins) —
the framework isn't rigged.
"""
from pathlib import Path

import pytest

from harness.eval import (ArmConfig, run_arm, run_eval, compare,
                          SINGLE_SHOT, VERIFIED_INFERENCE, FLAT_N)
from harness.oracle import PytestOracle
from harness.proposer import StubProposer, ProposerOutput, prompt_hash
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


class WeakPassAt1:
    """pass@1 ~0 (returns WRONG at temp 0) but pass@k rescues (CORRECT at high temp).
    Models a non-frontier model whose single-shot is weak but whose tail is fatter."""
    def __init__(self):
        self.model_ref = "weak-passat1"
        self._map = {0.0: WRONG, 0.4: WRONG, 0.8: CORRECT, 1.1: CORRECT}

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        text = self._map.get(round(temperature, 2), WRONG)
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


class StrongAlways:
    """pass@1 = 1.0 (always CORRECT). Single-shot already passes."""
    def __init__(self):
        self.model_ref = "strong-always"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text=CORRECT, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_harness_rescues_weak_model_beats_single_shot(task):
    """Where best-of-N rescues a weak pass@1, verified_inference > single_shot."""
    single = run_arm(SINGLE_SHOT, task, WeakPassAt1(), PytestOracle())
    verified = run_arm(VERIFIED_INFERENCE, task, WeakPassAt1(), PytestOracle())
    assert not single.passed, "weak pass@1 single-shot must fail"
    assert verified.passed, "best-of-N must rescue it"
    assert verified.oracle_calls > single.oracle_calls


def test_strong_model_no_artificial_advantage(task):
    """Where single-shot already passes, the harness gains nothing artificial."""
    single = run_arm(SINGLE_SHOT, task, StrongAlways(), PytestOracle())
    verified = run_arm(VERIFIED_INFERENCE, task, StrongAlways(), PytestOracle())
    assert single.passed and verified.passed


def test_compare_returns_match_when_harness_wins(task):
    reports = run_eval(
        [SINGLE_SHOT, VERIFIED_INFERENCE], [task],
        proposer_for=lambda arm, t: WeakPassAt1(),
        oracle_for=lambda t: PytestOracle())
    assert compare(reports) == "MATCH"


def test_compare_returns_drift_when_baseline_wins(task):
    """The whole-program falsifier: if single_shot wins, the thesis is DRIFT.
    Construct: single_shot uses StrongAlways (passes); verified uses a proposer
    that's weak even under best-of-N (always WRONG)."""
    class AlwaysWrongNoRescue:
        def __init__(self):
            self.model_ref = "always-wrong"
        def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
            return ProposerOutput(text=WRONG, model_ref=self.model_ref, seed=seed,
                                  prompt_hash=prompt_hash(prompt), cache="stub")
    reports = run_eval(
        [SINGLE_SHOT, VERIFIED_INFERENCE], [task],
        proposer_for=lambda arm, t: (StrongAlways() if arm.name == "single_shot"
                                     else AlwaysWrongNoRescue()),
        oracle_for=lambda t: PytestOracle())
    assert compare(reports) == "DRIFT", "framework must report DRIFT honestly when baseline wins"


def test_receipt_reproducibility_is_100_percent(task):
    """Every accept is re-checkable by construction (the witness re-runs the oracle)."""
    for arm in [SINGLE_SHOT, VERIFIED_INFERENCE, FLAT_N]:
        r = run_arm(arm, task, StrongAlways(), PytestOracle())
        assert r.receipt_reproducible


def test_budget_tracked_honestly(task):
    """single_shot = 1 oracle call; verified_inference (N=4) = 4 calls."""
    single = run_arm(SINGLE_SHOT, task, StrongAlways(), PytestOracle())
    verified = run_arm(VERIFIED_INFERENCE, task, StrongAlways(), PytestOracle())
    assert single.oracle_calls == 1
    assert verified.oracle_calls == 4


def test_eval_report_aggregation():
    from harness.eval import _aggregate, ArmResult
    rs = [ArmResult("a", "t1", True, 1, 1, 0.1),
          ArmResult("a", "t2", False, 4, 4, 0.5),
          ArmResult("a", "t3", True, 1, 1, 0.1)]
    rep = _aggregate("a", rs)
    assert rep.pass_rate == pytest.approx(2 / 3)
    assert rep.avg_oracle_calls == pytest.approx(6 / 3)
    assert rep.receipt_reproducibility == 1.0
