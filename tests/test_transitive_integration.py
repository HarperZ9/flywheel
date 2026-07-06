"""transitive witness — end-to-end over REAL ProofEnvelopes (not synthetic nodes).

Proves the closure works on the actual harness data model: run_loop stamps
`retrieved` citation edges onto every envelope, witness_envelope re-checks each,
and verify_frontier folds them. The load-bearing falsifier: tamper an ANCESTOR's
verified result and a descendant that CITES it must gap to UNVERIFIABLE, while an
independent result holds MATCH — criterion-conservation on live envelopes.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from harness.loop import run_loop
from harness.task import load_task, Retrieved
from harness.oracle import PytestOracle
from harness.witness import witness_envelope
from harness.transitive_witness import verify_frontier, MATCH, DRIFT, UNVERIFIABLE
from harness.proposer import prompt_hash, ProposerOutput

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


class FixedProposer:
    model_ref = "fixed"
    def __init__(self, text): self.text = text
    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text=self.text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="live")


def _mktask(tmp, tid, cites=None):
    t = load_task(TASK_DIR, workdir=tmp / tid)        # materializes the skeleton
    rets = [Retrieved(source=c, receipt=f"r{c}") for c in (cites or [])]
    return replace(t, task_id=tid, retrieved=rets)


def _rewitness_for(tasks_by_id):
    def rw(env):
        t = tasks_by_id[env.task_id]
        return witness_envelope(env, workdir=t.workdir,
                                candidate_path=t.candidate_path).verdict
    return rw


@pytest.fixture
def scenario(tmp_path):
    tA = _mktask(tmp_path, "A")
    tB = _mktask(tmp_path, "B", cites=["A"])           # B is grounded on A
    tC = _mktask(tmp_path, "C")                         # independent
    tasks = {"A": tA, "B": tB, "C": tC}
    envs = [run_loop(t, FixedProposer(CORRECT), PytestOracle(),
                     envelopes_dir=tmp_path / "env").envelope
            for t in (tA, tB, tC)]
    return envs, tasks


def test_clean_frontier_all_match(scenario):
    envs, tasks = scenario
    v = verify_frontier(envs, _rewitness_for(tasks))
    assert v == {"A": MATCH, "B": MATCH, "C": MATCH}


def test_ancestor_tamper_gaps_only_the_dependent(scenario):
    envs, tasks = scenario
    by_id = {e.task_id: e for e in envs}
    by_id["A"].candidate = "def add(a, b):\n    return a - b\n"   # A now wrong
    v = verify_frontier(envs, _rewitness_for(tasks))
    assert v["A"] == DRIFT, "A's re-witness must refute the tampered candidate"
    assert v["B"] == UNVERIFIABLE, "B cites A -> grounding drifted -> gap"
    assert v["C"] == MATCH, "C is independent -> must hold the line (localization)"


def test_citation_edges_come_from_real_envelopes(scenario):
    envs, _ = scenario
    envB = next(e for e in envs if e.task_id == "B")
    # run_loop actually stamped the citation onto the envelope
    assert any(r.get("source") == "A" for r in envB.retrieved)
