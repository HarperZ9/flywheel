"""M3-into-run_loop integration falsifier — the verified_inference arm, end-to-end.

run_loop with a search config runs best-of-N and emits a 'search' chain stage
carrying ALL k candidates (linear chain preserved). Tampering any candidate
entry breaks the search stage's content hash -> link to accept collapses. This
unblocks the real M7 eval: the verified_inference arm now runs through the
primary API, not just as a standalone capability.
"""
import copy
from pathlib import Path

import pytest

from harness.chain import validate_chain
from harness.eval import VERIFIED_INFERENCE
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import ProposerOutput, prompt_hash
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


class TempDiverse:
    def __init__(self):
        self.model_ref = "temp-diverse"
        self._map = {0.0: WRONG, 0.4: WRONG, 0.8: CORRECT, 1.1: CORRECT}

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        text = self._map.get(round(temperature, 2), WRONG)
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def test_search_mode_runs_best_of_n_and_accepts(task, tmp_path):
    r = run_loop(task, TempDiverse(), PytestOracle(),
                 envelopes_dir=tmp_path / "env", search=VERIFIED_INFERENCE)
    assert r.accepted
    assert r.envelope.candidate == CORRECT


def test_search_chain_stage_carries_all_candidates(task, tmp_path):
    r = run_loop(task, TempDiverse(), PytestOracle(),
                 envelopes_dir=tmp_path / "env", search=VERIFIED_INFERENCE)
    stages = [s["stage"] for s in r.envelope.chain]
    assert "search" in stages
    assert "propose" not in stages and "verify" not in stages
    search_stage = next(s for s in r.envelope.chain if s["stage"] == "search")
    assert search_stage["payload"]["n"] == 4
    assert len(search_stage["payload"]["candidates"]) == 4


def test_search_chain_validates_match(task, tmp_path):
    r = run_loop(task, TempDiverse(), PytestOracle(),
                 envelopes_dir=tmp_path / "env", search=VERIFIED_INFERENCE)
    v = validate_chain(r.envelope.chain)
    assert v.verdict == "MATCH", v.reason


def test_tamper_a_search_candidate_collapses_chain(task, tmp_path):
    r = run_loop(task, TempDiverse(), PytestOracle(),
                 envelopes_dir=tmp_path / "env", search=VERIFIED_INFERENCE)
    tampered = copy.deepcopy(r.envelope.chain)
    search_stage = next(s for s in tampered if s["stage"] == "search")
    search_stage["payload"]["candidates"][0]["verdict"] = "FORGED"
    v = validate_chain(tampered)
    assert v.verdict == "UNVERIFIABLE", "candidate-entry tamper must collapse the chain"


def test_single_mode_still_works_unchanged(task, tmp_path):
    from harness.proposer import StubProposer
    r = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env")
    assert r.accepted
    stages = [s["stage"] for s in r.envelope.chain]
    assert "propose" in stages and "verify" in stages and "search" not in stages
