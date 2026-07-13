"""developmental-flywheel falsifier — the model grows only on VERIFIED experience.

The oracle is the selection pressure: only PASS envelopes that re-witness MATCH
become training data. A tampered accept (candidate no longer passes) is excluded —
the environment never feeds the model its own unverified guesses. Every example is
receipted back to its proof envelope.
"""
from pathlib import Path

import pytest

from harness.loop import run_loop
from harness.task import load_task
from harness.oracle import PytestOracle
from harness.witness import witness_envelope
from harness.proposer import ProposerOutput, prompt_hash
from harness.developmental import curate, to_jsonl, corpus_stats, TrainingExample

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a - b\n"


class Fixed:
    model_ref = "fixed"
    def __init__(self, t): self.t = t
    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text=self.t, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="live")


def _rewitness(task):
    return lambda env: witness_envelope(env, workdir=task.workdir,
                                        candidate_path=task.candidate_path).verdict


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_verified_accept_becomes_a_training_example(task, tmp_path):
    r = run_loop(task, Fixed(CORRECT), PytestOracle(), envelopes_dir=tmp_path / "e")
    ex = curate([(r.envelope, task.prompt)], _rewitness(task))
    assert len(ex) == 1
    assert ex[0].completion.strip() == CORRECT.strip()
    assert ex[0].prompt == task.prompt and ex[0].source_receipt


def test_tampered_accept_is_excluded_from_nutrition(task, tmp_path):
    r = run_loop(task, Fixed(CORRECT), PytestOracle(), envelopes_dir=tmp_path / "e")
    r.envelope.candidate = WRONG                      # tamper: now wrong
    ex = curate([(r.envelope, task.prompt)], _rewitness(task))
    assert ex == [], "a tampered accept must not become training data"


def test_dedup_and_jsonl_and_stats(task, tmp_path):
    r = run_loop(task, Fixed(CORRECT), PytestOracle(), envelopes_dir=tmp_path / "e")
    ex = curate([(r.envelope, task.prompt), (r.envelope, task.prompt)], _rewitness(task))
    assert len(ex) == 1                               # deduped
    jsonl = to_jsonl(ex)
    assert '"source_receipt"' in jsonl and jsonl.count("\n") == 0
    st = corpus_stats(ex)
    assert st["n_examples"] == 1 and st["all_receipted"] is True


def test_non_pass_envelope_never_admitted(task, tmp_path):
    r = run_loop(task, Fixed(WRONG), PytestOracle(), envelopes_dir=tmp_path / "e")
    # a failing candidate produces a non-PASS envelope -> excluded regardless
    ex = curate([(r.envelope, task.prompt)], _rewitness(task))
    assert ex == []
