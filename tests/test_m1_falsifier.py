"""M1 falsifier (HARNESS-ROADMAP.md M1).

Two cases:
  1. Golden path: correct candidate -> PytestOracle PASS -> witness MATCH -> accept.
     A third party re-runs oracle_cmd and reproduces the verdict.
  2. Corruption: tamper the envelope's candidate after sealing -> witness MUST
     return DRIFT (hash mismatch), never MATCH. The binary-collapse guard.

If case 2 ever passes, the receipt chain is broken and M1 cannot promote.
"""
import json
from pathlib import Path

import pytest

from harness.envelope import ProofEnvelope, load_envelope
from harness.loop import run_loop
from harness.oracle import PytestOracle, StubOracle
from harness.proposer import StubProposer
from harness.task import load_task
from harness.witness import witness_envelope

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "workdir")


def test_golden_path_accepts_and_reproduces(task, tmp_path):
    proposer = StubProposer(CORRECT)
    oracle = PytestOracle()
    result = run_loop(task, proposer, oracle, envelopes_dir=tmp_path / "env")
    assert result.oracle.passed, result.oracle.stdout_excerpt
    assert result.witness.verdict == "MATCH", result.witness.reason
    assert result.accepted
    envs = list((tmp_path / "env").glob("*.json"))
    assert len(envs) == 1
    rechecked = witness_envelope(load_envelope(envs[0]), workdir=task.workdir,
                                 candidate_path=task.candidate_path)
    assert rechecked.verdict == "MATCH"


def test_failing_candidate_not_accepted(task, tmp_path):
    proposer = StubProposer(WRONG)
    oracle = PytestOracle()
    result = run_loop(task, proposer, oracle, envelopes_dir=tmp_path / "env")
    assert not result.oracle.passed
    assert not result.accepted
    assert list((tmp_path / "env").glob("*.json")) == []


def test_corrupted_envelope_collapses_to_drift(task, tmp_path):
    proposer = StubProposer(CORRECT)
    oracle = PytestOracle()
    result = run_loop(task, proposer, oracle, envelopes_dir=tmp_path / "env")
    env = result.envelope
    tampered = ProofEnvelope(
        **{**env.__dict__, "candidate": WRONG,
           "oracle_output_hash": env.oracle_output_hash})
    verdict = witness_envelope(tampered, workdir=task.workdir,
                               candidate_path=task.candidate_path)
    assert verdict.verdict == "DRIFT", verdict.reason
