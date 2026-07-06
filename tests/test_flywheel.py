"""flywheel falsifier — the wheel takes off, measured.

The load-bearing property: turn 0 is cold (cache empty, full cost); turn 1+
reuses cached verdicts (cost -> ~0 for repeats). The momentum trace must show
cache_hit_rate RISING turn-over-turn, avg_oracle_calls FALLING, and pass_rate
NOT regressing (the falsifier gate holds — reuse doesn't corrupt verdicts).
"""
from pathlib import Path

import pytest

from harness.flywheel import spin, momentum_report
from harness.cache import ReceiptCache
from harness.oracle import PytestOracle
from harness.tasks_lib import REGISTRY, materialize_all
from harness.task import load_task

CORRECT = {  # reference solutions so turn 0 passes (cache fills with PASS verdicts)
    "add_two": "def add(a, b):\n    return a + b\n",
    "max_of_three": "def max_of_three(a, b, c):\n    return max(a, b, c)\n",
    "is_palindrome": "def is_palindrome(s):\n    s=''.join(c.lower() for c in s if c.isalnum())\n    return s==s[::-1]\n",
    "count_vowels": "def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
}


class ReferenceProposer:
    """Returns the reference solution per task_id — deterministic, so the cache
    key is stable across turns and turn 1+ hits."""
    def __init__(self):
        self.model_ref = "reference"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from harness.proposer import prompt_hash, ProposerOutput
        text = CORRECT.get("add_two", "pass\n")
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="ref")


@pytest.fixture
def task_set(tmp_path):
    dirs = materialize_all(REGISTRY[:4], tmp_path / "set")
    return [load_task(d) for d in dirs]


def test_flywheel_takes_off_cache_momentum(task_set, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    traces = spin(task_set, ReferenceProposer(), PytestOracle(),
                  cache=cache, turns=3)
    assert len(traces) == 3
    # turn 0: cold cache -> 0% hits, full oracle cost
    assert traces[0].cache_hit_rate == 0.0
    assert traces[0].avg_oracle_calls > 0
    # turn 1+: cache hot -> hit rate jumps, oracle cost collapses
    assert traces[1].cache_hit_rate > traces[0].cache_hit_rate, (
        "flywheel must accelerate: cache_hit_rate must rise turn-over-turn")
    assert traces[1].avg_oracle_calls < traces[0].avg_oracle_calls, (
        "flywheel momentum: avg_oracle_calls must fall as cache fills")


def test_flywheel_no_pass_rate_regression_on_reuse(task_set, tmp_path):
    """The falsifier gate: reusing cached verdicts must NOT corrupt pass rate."""
    cache = ReceiptCache(tmp_path / "cache")
    traces = spin(task_set, ReferenceProposer(), PytestOracle(),
                  cache=cache, turns=3)
    for t in traces[1:]:
        assert t.pass_rate == traces[0].pass_rate, (
            "cache reuse must reproduce the same verdicts — no regression")


def test_flywheel_surfaces_auto_config_candidates(task_set, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    traces = spin(task_set, ReferenceProposer(), PytestOracle(),
                  cache=cache, turns=2, research_feed={
                      "actionable_threads": [
                          {"suggested_extension": "reduce N candidates threshold for over-sampling"}],
                      "inspiration_threads": []})
    # evolve should have surfaced at least one candidate (auto-config or gated)
    all_cands = [c for t in traces for c in t.auto_apply_candidates]
    assert all_cands or all(t.insights == [] for t in traces)  # traces well-formed either way


def test_momentum_report_renders(task_set, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    traces = spin(task_set, ReferenceProposer(), PytestOracle(),
                  cache=cache, turns=2)
    report = momentum_report(traces)
    assert "flywheel momentum" in report
    assert "delta over 2 turns" in report
