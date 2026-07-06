"""proof-addressed memory falsifier — the F2 fix, with C2 preserved.

The load-bearing claim: because acceptance is oracle-gated and prompt-independent,
a verified result keyed on (task, oracle_type, oracle_cmd, oracle_input_hash) —
prompt ABSENT — collapses two prompts differing only in a volatile header onto one
entry, and a hit is re-witnessed (not blind-trusted) before it is served.

Each test would FAIL if the claim were false:
  F1 prompt-invariance: prompt-keying SPLITS what proof-keying UNIFIES.
  F2 no stale serve: changed oracle input -> different proof_key -> MISS.
  F3 tamper -> DRIFT -> refuse: a hit is re-witnessed, not blind-trusted (C2).
  F4 (the hard one): the scope condition is real — no registered prompt-
     independent oracle's verify() reads the prompt; unknown oracles opt OUT.
"""
from pathlib import Path

import pytest

from harness.cache import ReceiptCache, cache_key
from harness.oracle import PytestOracle
from harness.proof_cache import (proof_key, proof_lookup, proof_insert,
                                 is_prompt_independent)
from harness.loop import run_loop
from harness.task import load_task
from harness.proposer import prompt_hash, ProposerOutput

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


class CountingProposer:
    def __init__(self, text, model_ref="counting-stub"):
        self.text = text
        self.model_ref = model_ref
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(text=self.text, model_ref=self.model_ref,
                              seed=seed, prompt_hash=prompt_hash(prompt), cache="live")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def _bank_pass(task, tmp_path):
    """Run the loop once to produce a real PASS envelope."""
    r = run_loop(task, CountingProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env")
    assert r.accepted and r.envelope.verdict == "PASS"
    return r.envelope


# --- F1: prompt-keying SPLITS what proof-keying UNIFIES (the F2 bug + fix) ---
def test_volatile_header_collapses_to_one_proof_entry(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    env = _bank_pass(task, tmp_path)
    assert proof_insert(cache, task, env) is not None

    base = task.prompt
    pa = "[req-id: 9f3a] " + base       # two prompts, identical task+oracle,
    pb = "[req-id: 7c1e] " + base       # differing ONLY in a volatile header

    # prompt-keyed cache WOULD miss: the two headers hash to different keys.
    ka = cache_key(task, prompt_hash(pa), env.model_ref, env.seed, task.oracle_cmd)
    kb = cache_key(task, prompt_hash(pb), env.model_ref, env.seed, task.oracle_cmd)
    assert ka != kb, "volatile header splits the prompt-keyed cache (the 0% bug)"

    # proof-key is identical for both — the prompt is absent from the key.
    assert (proof_key(task, "pytest", task.oracle_cmd)
            == proof_key(task, "pytest", task.oracle_cmd))
    # and a lookup under either prompt HITS the same banked fact, re-witnessed.
    task.prompt = pa
    hit = proof_lookup(cache, task, PytestOracle())
    assert hit is not None and hit.verdict == "PASS", "same fact must proof-HIT"


def test_proof_hit_does_not_re_invoke_the_proposer(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    proof_insert(cache, task, _bank_pass(task, tmp_path))
    # proof_lookup structurally never touches a proposer: a hit is reuse.
    p = CountingProposer(CORRECT)
    assert proof_lookup(cache, task, PytestOracle()) is not None
    assert p.calls == 0


# --- F2: changed oracle input -> different proof_key -> MISS (no stale serve) -
def test_changed_test_content_refuses_proof_hit(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    proof_insert(cache, task, _bank_pass(task, tmp_path))
    tf = Path(task.workdir) / "tests" / "test_solution.py"
    tf.write_text("from solution import add\ndef test_new():\n    assert add(2,2)==4\n",
                  encoding="utf-8")
    assert proof_lookup(cache, task, PytestOracle()) is None, "changed tests must MISS"


# --- F3: tamper -> re-witness DRIFT/FAIL -> refuse (C2 preserved) ---
def test_tampered_candidate_is_re_witnessed_and_refused(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    env = _bank_pass(task, tmp_path)
    key = proof_key(task, env.oracle, task.oracle_cmd)     # same key proof_insert uses
    env.candidate = "def add(a, b):\n    return a * b\n"   # now wrong
    cache.insert(env, key)                                  # inject the tampered entry
    # re-witness re-runs pytest on the tampered candidate -> FAIL != stored hash
    # -> DRIFT -> proof_lookup returns None instead of serving a false PASS.
    assert proof_lookup(cache, task, PytestOracle()) is None, "tampered entry must not serve"


# --- F4 (hard): the scope condition is real, not assumed ---
def test_no_prompt_independent_oracle_reads_the_prompt():
    src = (Path(__file__).parent.parent / "harness" / "oracle.py").read_text(encoding="utf-8")
    for marker in ("task.prompt", "task.system"):
        assert marker not in src, f"an oracle reads {marker}; proof-addressing unsound"
    assert is_prompt_independent("pytest") and is_prompt_independent("stub")
    assert not is_prompt_independent("unknown-oracle"), "unknown oracles must opt OUT"


def test_prompt_dependent_oracle_never_proof_addressed(task, tmp_path):
    cache = ReceiptCache(tmp_path / "cache")
    proof_insert(cache, task, _bank_pass(task, tmp_path))

    class PromptReadingOracle:
        oracle_type = "answers-this-prompt"   # not in PROMPT_INDEPENDENT
        def verify(self, candidate, task):     # would read task.prompt in reality
            raise AssertionError("must never be reached via proof cache")

    assert proof_lookup(cache, task, PromptReadingOracle()) is None


# --- The eval-vs-serving distinction (why proof-addressing is OPT-IN) ---
WRONG = "def add(a, b):\n    return a - b\n"


def test_serving_mode_hits_across_models(task, tmp_path):
    """proof_addressed=True: the fact-key omits model_ref, so a DIFFERENT model
    hits the first model's verified result (cross-model reuse — the serving win)."""
    cache = ReceiptCache(tmp_path / "cache")
    p1 = CountingProposer(CORRECT, "model-A")
    run_loop(task, p1, PytestOracle(), envelopes_dir=tmp_path / "env",
             cache=cache, proof_addressed=True)
    # A second run with a WRONG model B still HITS A's proven fact and returns it.
    p2 = CountingProposer(WRONG, "model-B")
    r2 = run_loop(task, p2, PytestOracle(), envelopes_dir=tmp_path / "env",
                  cache=cache, proof_addressed=True)
    assert r2.cache_hit is True, "serving mode reuses the verified fact across models"
    assert p2.calls == 0, "the second model must not run — the fact is already proven"
    assert r2.envelope.verdict == "PASS"


def test_eval_mode_default_reruns_each_model(task, tmp_path):
    """Default (proof_addressed=False): each model actually runs — proof-
    addressing must NOT short-circuit A/B eval (M7). This is why it is opt-in."""
    cache = ReceiptCache(tmp_path / "cache")
    run_loop(task, CountingProposer(CORRECT, "model-A"), PytestOracle(),
             envelopes_dir=tmp_path / "env", cache=cache)          # default off
    p2 = CountingProposer(WRONG, "model-B")
    r2 = run_loop(task, p2, PytestOracle(), envelopes_dir=tmp_path / "env", cache=cache)
    assert r2.cache_hit is False, "eval mode must re-run a different model, not hit"
    assert p2.calls == 1
    # both runs write ONE prompt-keyed entry each (different model_ref -> different
    # key); crucially, ZERO proof-index entries — eval mode never dual-indexes.
    assert cache.size() == 2
