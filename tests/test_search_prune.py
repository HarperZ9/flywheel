"""Duplicate pruning in search mode, opt-in.

Success criteria:
- normalize() ignores comments, whitespace and identifier names, and keeps
  structure;
- with prune_m = 2, a third copy of a wrong program is pruned (skips the oracle)
  while a distinct right program whose early prefix matches only one earlier
  candidate is kept and accepted;
- false-success control: the same pool with prune_m = 1 prunes the right
  program, so the fixture exercises the threshold;
- property: over random pools, a pruned candidate's niche always still has at
  least m live members, and at most 3 candidates are pruned;
- pruning is off by default, and pruned tokens are recorded in the search stage.
"""
from __future__ import annotations

import random

import pytest

from harness.eval import VERIFIED_INFERENCE
from harness.oracle import OracleResult
from harness.proposer import ProposerOutput, prompt_hash
from harness.search import best_of_n
from harness.search_prune import CHECKPOINTS, DuplicatePruner, niche_keys, normalize
from harness.task import Task

WRONG = "def add(a, b):\n    # sum\n    total = a * b\n    return total\n"
WRONG_RENAMED = "def add(x, y):\n    out = x * y\n    return out\n"
RIGHT = "def add(a, b):\n    total = a * b - a * b + a + b\n    return total\n"
TASK = Task(task_id="t", prompt="p", oracle="fn", oracle_cmd="fn", workdir=".",
            candidate_path="solution.py")


class Seq:
    model_ref = "seq"

    def __init__(self, texts):
        self.texts = list(texts)

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text=self.texts.pop(0), model_ref="seq", seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub",
                              usage={"completion_tokens": 11})


class Counting:
    oracle_type = "fn"

    def __init__(self):
        self.calls = []

    def verify(self, candidate, task):
        self.calls.append(candidate)
        ok = candidate == RIGHT
        return OracleResult(passed=ok, cmd="fn", output_hash="h", stdout_excerpt="",
                            rc=0 if ok else 1)


def test_normalize_ignores_names_comments_whitespace():
    assert normalize(WRONG) == normalize(WRONG_RENAMED)
    assert normalize(WRONG) != normalize(RIGHT)


def _run(m):
    oracle = Counting()
    sr = best_of_n(TASK, Seq([WRONG, WRONG_RENAMED, WRONG, RIGHT]), oracle,
                   temps=[0.0, 0.4, 0.8, 1.1], prune_m=m)
    return sr, oracle


def test_m2_prunes_the_third_copy_and_keeps_the_distinct_right_answer():
    sr, oracle = _run(2)
    assert [c.pruned for c in sr.candidates] == [False, False, True, False]
    assert len(oracle.calls) == 3
    assert sr.verdict == "PASS" and sr.accepted.text == RIGHT
    assert (sr.pruned, sr.pruned_tokens) == (1, 11)


def test_control_m1_loses_the_right_answer():
    sr, _ = _run(1)
    assert sr.candidates[-1].pruned
    assert sr.accepted is None


def test_off_by_default():
    sr = best_of_n(TASK, Seq([WRONG, WRONG, WRONG, RIGHT]), Counting(),
                   temps=[0.0, 0.4, 0.8, 1.1])
    assert sr.pruned == 0 and not any(c.pruned for c in sr.candidates)
    assert VERIFIED_INFERENCE.prune_m is None


@pytest.mark.parametrize("seed", range(25))
def test_property_pruning_keeps_m_live_members(seed):
    rng = random.Random(seed)
    pool = [rng.choice([WRONG, WRONG_RENAMED, RIGHT, "def add(a, b):\n    return b + a\n"])
            for _ in range(10)]
    m = rng.choice([1, 2, 3])
    pruner, live = DuplicatePruner(m), []
    for text in pool:
        if pruner.check(text):
            keys = niche_keys(text)
            assert any(sum(niche_keys(x)[i] == keys[i] for x in live) >= m
                       for i in range(len(CHECKPOINTS)))
        else:
            live.append(text)
    assert pruner.pruned <= 3


def test_bad_m_is_refused():
    with pytest.raises(ValueError):
        DuplicatePruner(0)


def test_search_stage_records_pruning(tmp_path):
    from dataclasses import replace
    from pathlib import Path

    from harness.loop import run_loop
    from harness.oracle import PytestOracle
    from harness.task import load_task
    correct = "def add(a, b):\n    return a + b\n"
    task = load_task(Path(__file__).parent.parent / "tasks" / "example_pass",
                     workdir=tmp_path / "w")
    r = run_loop(task, Seq([WRONG, WRONG_RENAMED, WRONG, correct]), PytestOracle(),
                 envelopes_dir=tmp_path / "env",
                 search=replace(VERIFIED_INFERENCE, prune_m=2))
    stage = next(s for s in r.envelope.chain if s["stage"] == "search")
    assert stage["payload"]["pruning"]["pruned"] == 1
    assert stage["payload"]["pruning"]["pruned_tokens"] == 11
    assert [c["verdict"] for c in stage["payload"]["candidates"]][2] == "PRUNED"
    assert r.accepted
