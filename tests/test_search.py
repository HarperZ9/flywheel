"""M3 best-of-N falsifier (harness/search.py — pass@N amplification + voice-cap).

Three decisive cases (HARNESS-ROADMAP M3 falsifier):
  1. A task where correlated-N converges wrong: diversified sampling must find
     the right answer (PASS) OR return UNVERIFIABLE — never confident-wrong.
  2. Correlated wrong-attractor with no diversity escape -> UNVERIFIABLE.
  3. Genuinely diverse failure -> honest FAIL.
Plus the correlation detector flags near-identical candidate sets.
"""
from pathlib import Path

import pytest

from harness.oracle import PytestOracle, StubOracle
from harness.search import (best_of_n, jaccard, max_pairwise_correlation,
                            DEFAULT_TEMPS, CORRELATION_THRESHOLD)
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"
WRONG2 = "def add(a, b):\n    return a - b\n"
WRONG3 = "def add(a, b):\n    return a / b\n"


class TempDiverseProposer:
    """Returns CORRECT at high temperature, WRONG variants at low temperature.
    Models a model whose pass@1 is low but pass@k rescues it via diversity."""
    def __init__(self):
        self.model_ref = "temp-diverse"
        self._map = {0.0: WRONG, 0.4: WRONG2, 0.8: CORRECT, 1.1: WRONG3}

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from harness.proposer import prompt_hash, ProposerOutput
        text = self._map.get(round(temperature, 2), WRONG)
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


class AlwaysWrongProposer:
    """Always returns the SAME wrong answer regardless of temperature — models
    wrong-attractor convergence (correlated-N, §8)."""
    def __init__(self):
        self.model_ref = "always-wrong"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from harness.proposer import prompt_hash, ProposerOutput
        return ProposerOutput(text=WRONG, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


class DiverseWrongProposer:
    """Returns DIFFERENT wrong answers at each temperature — models genuine
    diverse failure (honest FAIL, not wrong-attractor)."""
    def __init__(self):
        self.model_ref = "diverse-wrong"
        self._map = {0.0: WRONG, 0.4: WRONG2, 0.8: WRONG3,
                     1.1: "def add(a, b):\n    return None\n"}

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from harness.proposer import prompt_hash, ProposerOutput
        text = self._map.get(round(temperature, 2), WRONG)
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_diversified_sampling_finds_right_answer(task):
    """pass@k rescue: low pass@1 but diversity finds the PASS among wrongs."""
    r = best_of_n(task, TempDiverseProposer(), PytestOracle())
    assert r.verdict == "PASS"
    assert r.accepted is not None
    assert r.accepted.text == CORRECT


def test_correlated_wrong_attractor_is_unverifiable(task):
    """§8 trap: all candidates same wrong answer -> UNVERIFIABLE, not FAIL."""
    r = best_of_n(task, AlwaysWrongProposer(), PytestOracle())
    assert r.verdict == "UNVERIFIABLE"
    assert r.correlation >= CORRELATION_THRESHOLD
    assert r.accepted is None


def test_genuinely_diverse_failure_is_honest_fail(task):
    """Different wrong answers, no pass, low correlation -> honest FAIL."""
    r = best_of_n(task, DiverseWrongProposer(), PytestOracle())
    assert r.verdict == "FAIL"
    assert r.correlation < CORRELATION_THRESHOLD
    assert r.accepted is None


def test_never_confident_wrong(task):
    """The M3 falsifier core: no path produces a confident-wrong verdict.
    Every no-pass outcome is either FAIL (diverse) or UNVERIFIABLE (correlated)."""
    for proposer in (AlwaysWrongProposer(), DiverseWrongProposer()):
        r = best_of_n(task, proposer, PytestOracle())
        assert r.verdict in ("FAIL", "UNVERIFIABLE"), (
            f"must never be confident-wrong; got {r.verdict}")


def test_jaccard_and_correlation_detector():
    assert jaccard("a b c", "a b c") == 1.0
    assert jaccard("a b c", "d e f") == 0.0
    assert max_pairwise_correlation(["a b", "a b", "x y z"]) == 1.0
    assert max_pairwise_correlation(["a b c", "d e f", "g h i"]) == 0.0


def test_best_of_n_uses_all_default_temps(task):
    r = best_of_n(task, AlwaysWrongProposer(), PytestOracle())
    assert len(r.candidates) == len(DEFAULT_TEMPS)
    assert [c.temperature for c in r.candidates] == DEFAULT_TEMPS
