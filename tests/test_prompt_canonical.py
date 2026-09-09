"""Prompt cache keys are exact by default.

Volatile transport metadata can improve hit rate only after a caller has already
separated it from author content. Lexical guessing is unsafe because issue IDs,
timestamps, attribution lines, blank lines, and indentation can all be part of a
user's task.
"""
from pathlib import Path

import pytest

from harness.cache import ReceiptCache, canonical_prompt
from harness.oracle import PytestOracle
from harness.loop import run_loop
from harness.task import load_task
from harness.proposer import prompt_hash, ProposerOutput

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


class CountingProposer:
    model_ref = "counting"
    def __init__(self, text): self.text = text; self.calls = 0
    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(text=self.text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="live")


def test_canonical_prompt_is_exact_by_default():
    prompts = [
        "X-Request-Id: INC0010001",
        "2026-09-08T10:00:00Z",
        "Co-Authored-By: Alice <alice@example.test>",
        "Inspect [request_id: INC0010001]",
        "Implement add(a,b).\n\n    Preserve indentation.",
    ]
    for prompt in prompts:
        assert canonical_prompt(prompt) == prompt


def test_trusted_metadata_stripping_requires_explicit_opt_in():
    a = "[req-id: 9f3a2b] \nImplement add(a,b).\nCo-Authored-By: bot <x@y>"
    b = "[req-id: 7c1e00] \nImplement add(a,b).\nCo-Authored-By: bot <z@w>"
    assert canonical_prompt(a) != canonical_prompt(b)
    assert (canonical_prompt(a, strip_trusted_metadata=True)
            == canonical_prompt(b, strip_trusted_metadata=True)
            == "Implement add(a,b).")
    assert canonical_prompt("Implement sub(a,b).", strip_trusted_metadata=True) != canonical_prompt(
        a, strip_trusted_metadata=True)


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_opaque_id_semantic_change_misses_default_path(task, tmp_path):
    cache = ReceiptCache(tmp_path / "c")
    task.prompt = "X-Request-Id: INC0010001"
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "e", cache=cache)

    task.prompt = "X-Request-Id: INC0010002"
    p2 = CountingProposer(WRONG)
    r2 = run_loop(task, p2, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)

    assert r2.cache_hit is False
    assert p2.calls == 1
    assert r2.accepted is False
    assert r2.envelope.candidate == WRONG


def test_semantic_timestamp_and_attribution_changes_miss_default_path(task, tmp_path):
    cache = ReceiptCache(tmp_path / "c")
    task.prompt = "2026-09-08T10:00:00Z\nCo-Authored-By: Alice <a@example.test>"
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "e", cache=cache)

    task.prompt = "2026-09-09T10:00:00Z\nCo-Authored-By: Bob <b@example.test>"
    p2 = CountingProposer(WRONG)
    r2 = run_loop(task, p2, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)

    assert r2.cache_hit is False
    assert p2.calls == 1
    assert r2.accepted is False


def test_blank_lines_and_indentation_are_key_material(task, tmp_path):
    cache = ReceiptCache(tmp_path / "c")
    task.prompt = "Implement add(a,b).\n\n    Keep the indented line."
    run_loop(task, CountingProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "e", cache=cache)

    task.prompt = "Implement add(a,b).\nKeep the indented line."
    p2 = CountingProposer(WRONG)
    r2 = run_loop(task, p2, PytestOracle(), envelopes_dir=tmp_path / "e", cache=cache)

    assert r2.cache_hit is False
    assert p2.calls == 1
    assert r2.accepted is False
