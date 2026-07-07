"""The end-to-end closure falsifier — transitive witness ON the critical path.

The three arms the increment lives or dies by (all on REAL envelopes through
run_loop, not DepNode fixtures):
  1. Tampered ancestor A re-witnesses to DRIFT (closure sees the tamper).
  2. Task B that CITES A returns UNVERIFIABLE (gap, not glut) and is NOT
     accepted — even though B's own oracle passes locally.
  3. Independent task C stays MATCH/accepted (localization: unrelated drift
     never touches it).
FAIL modes (any one kills the increment): A stays MATCH after tamper; B
accepts / reports MATCH; C flips.

Plus the positive control (citing a HEALTHY ancestor conserves MATCH — without
it the wire could hard-code "citing -> unverifiable") and the two fail-closed
arms (no stored envelope / no oracle environment -> UNVERIFIABLE, never MATCH,
and never a fake re-run in the wrong workdir).
"""
import json
from pathlib import Path

import pytest

from harness.envelope import load_envelope
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import Retrieved, load_task
from harness.witness import witness_envelope

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


def _run_ancestor(tmp_path):
    """Seal ancestor A into the shared envelope store; return (task, env_path)."""
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = "anc_a"
    r = run_loop(a, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env")
    assert r.accepted
    (path,) = (tmp_path / "env").glob("anc_a-*.json")
    return a, path


def _citing_task(tmp_path, name, source):
    b = load_task(TASK_DIR, workdir=tmp_path / f"ws_{name}")
    b.task_id = name
    b.retrieved = [Retrieved(source=source, receipt="envelope")]
    return b


def _tamper(env_path):
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d["oracle_output_hash"] = "0" * len(d["oracle_output_hash"])
    env_path.write_text(json.dumps(d), encoding="utf-8")


def test_positive_control_healthy_grounding_conserves_match(tmp_path):
    a, _ = _run_ancestor(tmp_path)
    b = _citing_task(tmp_path, "dep_b", a.task_id)
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True,
                 grounding_workdirs={a.task_id: (a.workdir, a.candidate_path)})
    assert r.grounding is not None
    assert r.grounding["verdicts"][a.task_id] == "MATCH"
    assert r.grounding["verdict"] == "MATCH"
    assert r.accepted


def test_arm1_tampered_ancestor_rewitnesses_to_drift(tmp_path):
    a, path = _run_ancestor(tmp_path)
    _tamper(path)
    v = witness_envelope(load_envelope(path), workdir=a.workdir,
                         candidate_path=a.candidate_path)
    assert v.verdict == "DRIFT", v.reason


def test_arm2_citing_a_drifted_ancestor_is_unverifiable_not_accepted(tmp_path):
    a, path = _run_ancestor(tmp_path)
    _tamper(path)
    b = _citing_task(tmp_path, "dep_b", a.task_id)
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True,
                 grounding_workdirs={a.task_id: (a.workdir, a.candidate_path)})
    assert r.oracle.passed                       # B's OWN oracle passes locally
    assert r.witness.verdict == "MATCH"          # B's OWN receipt re-checks
    assert r.grounding["verdicts"][a.task_id] == "DRIFT"       # glut, localized
    assert r.grounding["verdict"] == "UNVERIFIABLE"            # gap, not glut
    assert not r.accepted
    # a poisoned result must never be sealed into the store
    assert list((tmp_path / "env").glob("dep_b-*.json")) == []


def test_arm3_independent_task_is_untouched_by_the_drift(tmp_path):
    a, path = _run_ancestor(tmp_path)
    _tamper(path)
    c = load_task(TASK_DIR, workdir=tmp_path / "ws_c")
    c.task_id = "indep_c"                        # cites nothing
    r = run_loop(c, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.witness.verdict == "MATCH"
    assert r.accepted
    assert r.grounding is None                   # no citations -> no closure gate


def test_failclosed_missing_stored_envelope_is_unverifiable(tmp_path):
    _run_ancestor(tmp_path)                      # store exists but not this id
    b = _citing_task(tmp_path, "dep_b", "ghost_ancestor")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdict"] == "UNVERIFIABLE"
    assert not r.accepted
    assert "no stored envelope" in r.grounding["reasons"]["ghost_ancestor"]


def test_failclosed_no_oracle_environment_is_unverifiable_not_fake_rerun(tmp_path):
    a, _ = _run_ancestor(tmp_path)
    b = _citing_task(tmp_path, "dep_b", a.task_id)
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)  # no workdirs
    assert r.grounding["verdicts"][a.task_id] == "UNVERIFIABLE"  # not MATCH, not DRIFT
    assert r.grounding["verdict"] == "UNVERIFIABLE"
    assert not r.accepted
    assert "fail closed" in r.grounding["reasons"][a.task_id]


def test_grounding_stage_is_sealed_into_the_chain(tmp_path):
    a, _ = _run_ancestor(tmp_path)
    b = _citing_task(tmp_path, "dep_b", a.task_id)
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True,
                 grounding_workdirs={a.task_id: (a.workdir, a.candidate_path)})
    stages = [s["stage"] for s in r.envelope.chain]
    assert "grounding" in stages
    g = next(s for s in r.envelope.chain if s["stage"] == "grounding")
    assert g["verdict"] == "MATCH"
    assert g["payload"]["verdicts"][a.task_id] == "MATCH"
