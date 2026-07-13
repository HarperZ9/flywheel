"""M5 receipt-cache falsifier (harness/cache.py — the compounding asset).

The cache is the genuine exponential: the more the harness runs, the higher the
hit rate, the cheaper each subsequent task. Its invariants are load-bearing:
  - Same query twice -> second is a HIT at ~0 cost (proposer NOT called).
  - Any key-component drift (model, seed, prompt) -> MISS.
  - Changed test content -> MISS (never serves a stale verdict).
"""
from pathlib import Path

import pytest

from harness.cache import ReceiptCache, cache_key, oracle_input_hash
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


class CountingProposer:
    def __init__(self, text, model_ref="counting-stub"):
        self._text = text
        self.calls = 0
        self.model_ref = model_ref

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        from harness.proposer import prompt_hash, ProposerOutput
        return ProposerOutput(text=self._text, model_ref=self.model_ref,
                              seed=seed, prompt_hash=prompt_hash(prompt),
                              cache="stub")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_repeated_query_is_cache_hit_skipping_proposer(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    p1 = CountingProposer(CORRECT)
    run_loop(task, p1, PytestOracle(), envelopes_dir=tmp_path / "env", cache=cache)
    assert p1.calls == 1
    r2 = run_loop(task, p1, PytestOracle(), envelopes_dir=tmp_path / "env", cache=cache)
    assert r2.cache_hit is True
    assert p1.calls == 1, "proposer must not be called on a cache hit"
    assert r2.oracle is None and r2.witness is None


def test_different_candidate_is_cache_miss(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    run_loop(task, CountingProposer(CORRECT, "model-correct"), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)
    assert cache.size() == 1
    p2 = CountingProposer(WRONG, "model-wrong")
    r2 = run_loop(task, p2, PytestOracle(),
                  envelopes_dir=tmp_path / "env", cache=cache)
    assert r2.cache_hit is False
    assert p2.calls == 1


def test_changed_test_content_is_miss_no_stale_serve(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)
    h_before = oracle_input_hash(task)
    test_file = Path(task.workdir) / "tests" / "test_solution.py"
    test_file.write_text("from solution import add\ndef test_new():\n    assert add(1,1)==2\n")
    h_after = oracle_input_hash(task)
    assert h_before != h_after, "test-content change must alter oracle_input_hash"
    p2 = CountingProposer(CORRECT)
    r2 = run_loop(task, p2, PytestOracle(),
                  envelopes_dir=tmp_path / "env", cache=cache)
    assert r2.cache_hit is False, "changed tests must MISS, never serve stale verdict"
    assert p2.calls == 1


def test_cache_key_is_deterministic(task):
    k1 = cache_key(task, "ph1", "model-a", 7, "pytest")
    k2 = cache_key(task, "ph1", "model-a", 7, "pytest")
    assert k1 == k2
    k3 = cache_key(task, "ph1", "model-b", 7, "pytest")
    assert k1 != k3, "different model_ref must produce a different key"
