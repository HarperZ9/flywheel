"""F2 falsifier — volatile prompt headers must not poison the prompt-keyed cache.

The bug (from the 2026-07-06 dive): agent clients prepend a per-turn attribution
header, so prompt_hash changes every turn -> the cache misses on every agent
request (0% hit rate). Fix: canonicalize the prompt at the cache-KEY site only.

Properties:
  1. Two prompts differing ONLY in a volatile header collapse to one key -> a
     second run is a cache HIT (proposer not called), across the DEFAULT prompt-
     keyed path (no proof-addressing needed).
  2. A prompt differing in the SEMANTIC BODY still misses (no false dedup).
  3. Provenance survives: the stored envelope keeps the REAL prompt_hash, not the
     canonicalized one.
"""
from pathlib import Path

import pytest

from harness.cache import canonical_prompt
from harness.oracle import PytestOracle
from harness.loop import run_loop
from harness.task import load_task
from harness.proposer import prompt_hash, ProposerOutput

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


class CountingProposer:
    model_ref = "counting"
    def __init__(self, text): self.text = text; self.calls = 0
    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(text=self.text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="live")


def test_canonical_strips_volatile_keeps_body():
    a = "[req-id: 9f3a2b] \nImplement add(a,b).\nCo-Authored-By: bot <x@y>"
    b = "[req-id: 7c1e00] \nImplement add(a,b).\nCo-Authored-By: bot <z@w>"
    assert canonical_prompt(a) == canonical_prompt(b) == "Implement add(a,b)."
    # a semantic change survives canonicalization
    assert canonical_prompt("Implement sub(a,b).") != canonical_prompt(a)


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_volatile_header_is_a_cache_hit_default_path(task, tmp_path):
    from harness.cache import ReceiptCache
    cache = ReceiptCache(tmp_path / "c")
    p = CountingProposer(CORRECT)
    # turn 1: attribution header A
    task.prompt = "[req-id: aaa111] Implement add(a,b)."
    run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)
    assert p.calls == 1
    # turn 2: SAME task, different volatile header -> must HIT (no re-propose)
    task.prompt = "[req-id: bbb222] Implement add(a,b)."
    r2 = run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)
    assert r2.cache_hit is True, "volatile-header-only change must hit the cache"
    assert p.calls == 1, "proposer must not run again on a volatile-only change"


def test_semantic_change_still_misses(task, tmp_path):
    from harness.cache import ReceiptCache
    cache = ReceiptCache(tmp_path / "c")
    p = CountingProposer(CORRECT)
    task.prompt = "[req-id: aaa111] Implement add(a,b)."
    run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)
    task.prompt = "[req-id: bbb222] Implement a DIFFERENT function entirely."
    r2 = run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)
    assert r2.cache_hit is False, "a real body change must miss (no false dedup)"
    assert p.calls == 2
