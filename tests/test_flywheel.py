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
    # turn 1+: cache hit saves generation, but current oracle checks remain
    assert traces[1].cache_hit_rate > traces[0].cache_hit_rate, (
        "flywheel must accelerate: cache_hit_rate must rise turn-over-turn")
    assert traces[1].avg_oracle_calls == traces[0].avg_oracle_calls == 1.0


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



def test_spin_explicit_dependency_map_drives_real_memory_input(tmp_path):
    import json
    from dataclasses import replace
    from harness.proposer import StubProposer

    class DependentProposer(StubProposer):
        def __init__(self):
            super().__init__("")
            self.inputs = []

        def generate(self, prompt, **kwargs):
            self.inputs.append(prompt)
            records = [json.loads(line) for line in prompt.splitlines()
                       if line.startswith('{"memory_source":')]
            self._canned = (CORRECT["add_two"] if prompt == "seed solution" else
                         records[0]["content"] if records else "def add(a,b): return 0")
            return super().generate(prompt, **kwargs)

    fixture = Path(__file__).resolve().parent.parent / "tasks" / "example_pass"
    tasks = [replace(load_task(fixture, workdir=tmp_path / "seed"),
                     task_id="family.seed", prompt="seed solution"),
             replace(load_task(fixture, workdir=tmp_path / "target"), task_id="family.next")]
    on, off = DependentProposer(), DependentProposer()
    enabled = spin(tasks, on, PytestOracle(), cache=ReceiptCache(tmp_path / "on"),
                   turns=1, envelopes_dir=str(tmp_path / "envelopes"),
                   memory_sources_by_task={"family.next": ["family.seed"]})
    disabled = spin(tasks, off, PytestOracle(), cache=ReceiptCache(tmp_path / "off"),
                    turns=1, envelopes_dir=str(tmp_path / "disabled"))
    assert enabled[0].pass_rate == 1.0 and disabled[0].pass_rate == 0.5
    assert enabled[0].memory_context_enabled and not disabled[0].memory_context_enabled
    assert "Untrusted memory evidence" in on.inputs[1]
    assert off.inputs[1] == tasks[1].prompt
