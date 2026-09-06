"""The fresh-environment fallback, and the asymmetry that makes it safe.

`recheck_grounding` used to need a caller-supplied workdir for every cited
ancestor, so `grounding_recheck` could not be turned on by default: fail-closed
plus a missing workdir marked every grounded task UNVERIFIABLE. The fallback
rebuilds the environment from the ancestor's own receipt.

What it must NOT become is a second way to be sure. Reproducing the stored
canonical hash in a bare directory is positive evidence the environment was
sufficient. Failing to reproduce it is not evidence of anything, because a
missing fixture and a real tamper are the same observation from here. So the
arm that matters most below is the tampered one: it must come back
UNVERIFIABLE, never DRIFT, and must still block acceptance.
"""
import json
import tempfile
from pathlib import Path

import pytest

from harness.envelope import ProofEnvelope, load_envelope
from harness.grounding import _safe_relative, recheck_grounding
from harness.oracle_inputs import restore
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import Retrieved, Task, load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"

# A candidate that carries its own test, so `pytest <candidate>` needs nothing
# else on disk. This is the shape the fallback can actually confirm.
SELF_CONTAINED = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)
BROKEN = SELF_CONTAINED.replace("return a + b", "return a * b")


def _self_contained_task(tmp_path, task_id):
    ws = tmp_path / ("ws_" + task_id)
    ws.mkdir(parents=True, exist_ok=True)
    return Task(
        task_id=task_id,
        prompt="unused: the proposer is a stub",
        oracle="pytest",
        oracle_cmd="python -m pytest sc_solution.py",
        workdir=str(ws),
        candidate_path="sc_solution.py",
    )


def _seal(task, tmp_path, candidate=SELF_CONTAINED):
    r = run_loop(task, StubProposer(candidate), PytestOracle(),
                 envelopes_dir=tmp_path / "env")
    (path,) = (tmp_path / "env").glob(task.task_id + "-*.json")
    return r, path


def _citing(tmp_path, name, source, task_dir=TASK_DIR):
    b = load_task(task_dir, workdir=tmp_path / ("ws_" + name))
    b.task_id = name
    b.retrieved = [Retrieved(source=source, receipt="envelope")]
    return b


def _refile(env_path):
    """Rename a rewritten receipt to the content hash it now has.

    Receipts are filed under their own hash and a mismatch is refused before
    any oracle runs, so a test that wants the re-run to happen has to hand the
    store a self-consistent receipt. The refusal itself is a separate property,
    covered in test_grounding_receipt_integrity.py.
    """
    refiled = env_path.with_name("%s-%s.json" % (
        env_path.name.rsplit("-", 1)[0], load_envelope(env_path).content_hash()))
    env_path.rename(refiled)
    return refiled


def _retamper(env_path, candidate):
    """Reseal the stored envelope around a different candidate, leaving the
    recorded hash alone. This is the tamper a re-run is supposed to catch."""
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d["candidate"] = candidate
    env_path.write_text(json.dumps(d), encoding="utf-8")
    return _refile(env_path)


def test_self_contained_ancestor_verifies_with_no_workdir_supplied(tmp_path):
    """The point of the change: no caller input, and the ancestor still MATCHes."""
    a = _self_contained_task(tmp_path, "anc_sc")
    r_a, _ = _seal(a, tmp_path)
    assert r_a.accepted
    b = _citing(tmp_path, "dep_b", "anc_sc")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_sc"] == "MATCH"
    assert r.grounding["verdict"] == "MATCH"
    assert r.accepted
    assert "fresh environment" in r.grounding["reasons"]["anc_sc"]


def test_tampered_ancestor_is_unverifiable_not_drift(tmp_path):
    """The control. A fresh-environment mismatch cannot tell a tamper from a
    missing fixture, so it must not claim to have caught one. Safety is kept by
    UNVERIFIABLE still failing closed, not by naming the ancestor guilty."""
    a = _self_contained_task(tmp_path, "anc_sc")
    _, env_path = _seal(a, tmp_path)
    _retamper(env_path, BROKEN)
    b = _citing(tmp_path, "dep_b", "anc_sc")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_sc"] == "UNVERIFIABLE"
    assert r.grounding["verdicts"]["anc_sc"] != "DRIFT"
    assert not r.accepted
    assert "does not separate drift from a missing fixture" \
        in r.grounding["reasons"]["anc_sc"]


def test_fixture_dependent_ancestor_verifies_from_its_carried_inputs(tmp_path):
    """The arm that gives the fallback reach on real work. example_pass runs
    `pytest tests/`, so its candidate alone rebuilds nothing; carrying the
    fixture set is what lets it re-run. Every task in this repo has this shape,
    so without this the mechanism confirms none of them."""
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = "anc_fixtures"
    r_a, env_path = _seal(a, tmp_path, candidate=CORRECT)
    assert r_a.accepted
    stored = load_envelope(env_path)
    assert "tests/test_solution.py" in stored.oracle_inputs
    assert "solution.py" not in stored.oracle_inputs   # the candidate travels once
    b = _citing(tmp_path, "dep_b", "anc_fixtures")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_fixtures"] == "MATCH"
    assert r.accepted


def test_ancestor_with_no_carried_inputs_stays_unverifiable(tmp_path):
    """Capture turned off leaves a fixture-dependent ancestor unrebuildable.
    That must still read as unconfirmed, never as drift."""
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = "anc_bare"
    r_a = run_loop(a, StubProposer(CORRECT), PytestOracle(),
                   envelopes_dir=tmp_path / "env", capture_oracle_inputs=False)
    assert r_a.accepted
    b = _citing(tmp_path, "dep_b", "anc_bare")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_bare"] == "UNVERIFIABLE"
    assert r.grounding["verdicts"]["anc_bare"] != "DRIFT"
    assert not r.accepted


def test_a_receipt_cannot_carry_its_own_answer_key(tmp_path):
    """canonical_hash reads outcomes back out of the junit file, so a receipt
    allowed to ship one would hand the fresh directory the answer before the
    oracle ran. Capture skips it and restore refuses it, because restore reads
    a file someone else wrote."""
    a = load_task(TASK_DIR, workdir=tmp_path / "ws_a")
    a.task_id = "anc_junit"
    _, env_path = _seal(a, tmp_path, candidate=CORRECT)
    d = json.loads(env_path.read_text(encoding="utf-8"))
    assert "_oracle_junit.xml" not in d["oracle_inputs"]
    # now plant one anyway, the way a hostile republisher would
    d["oracle_inputs"]["_oracle_junit.xml"] = "<testsuites/>"
    d["oracle_inputs"]["tests/__pycache__/x.py"] = "raise SystemExit(0)"
    env_path.write_text(json.dumps(d), encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        restore(load_envelope(env_path).oracle_inputs, td)
        planted = [p.name for p in Path(td).rglob("*") if p.is_file()]
    assert "_oracle_junit.xml" not in planted
    assert "x.py" not in planted


def test_envelope_sealed_before_the_field_existed_still_loads(tmp_path):
    """Back-compat, both halves: an old receipt deserialises, and its empty
    candidate_path gives the fallback nothing to run, so it fails closed."""
    a = _self_contained_task(tmp_path, "anc_sc")
    _, env_path = _seal(a, tmp_path)
    d = json.loads(env_path.read_text(encoding="utf-8"))
    d.pop("candidate_path")
    d.pop("oracle_inputs")
    env_path.write_text(json.dumps(d), encoding="utf-8")
    # an old store filed old receipts under the hashes they had at the time
    old = load_envelope(_refile(env_path))
    assert old.candidate_path == ""
    assert old.oracle_inputs == {}
    b = _citing(tmp_path, "dep_b", "anc_sc")
    r = run_loop(b, StubProposer(CORRECT), PytestOracle(),
                 envelopes_dir=tmp_path / "env", grounding_recheck=True)
    assert r.grounding["verdicts"]["anc_sc"] == "UNVERIFIABLE"
    assert "no usable candidate path" in r.grounding["reasons"]["anc_sc"]


def test_fallback_can_be_switched_off(tmp_path):
    """The pre-2026-09-06 behaviour is still reachable for a caller who wants
    the workdir contract enforced rather than reconstructed."""
    a = _self_contained_task(tmp_path, "anc_sc")
    _seal(a, tmp_path)
    b_env = ProofEnvelope(
        task_id="dep_b", candidate=CORRECT, oracle="pytest", oracle_cmd="x",
        oracle_output_hash="h", verdict="PASS", model_ref="stub", seed=0,
        prompt_hash="p", budget_spent={},
        retrieved=[{"source": "anc_sc", "receipt": "envelope"}])
    off = recheck_grounding(b_env, "MATCH", envelopes_dir=tmp_path / "env",
                            workdirs={}, fresh_env_retry=False)
    assert off["verdicts"]["anc_sc"] == "UNVERIFIABLE"
    assert "fail closed" in off["reasons"]["anc_sc"]
    on = recheck_grounding(b_env, "MATCH", envelopes_dir=tmp_path / "env",
                           workdirs={})
    assert on["verdicts"]["anc_sc"] == "MATCH"


@pytest.mark.parametrize("hostile", [
    "../escape.py", "../../escape.py", "a/../../escape.py",
    "/etc/passwd", "C:/Windows/x.py", "sub\\escape.py", "", ".", "..",
])
def test_hostile_candidate_path_is_refused_not_sanitised(hostile):
    """A stored envelope is attacker-reachable, and this value names a file we
    are about to write. Refusing costs a confirmation; rewriting it into
    something that still writes somewhere invents an environment nobody
    sealed."""
    assert _safe_relative(hostile) is None


@pytest.mark.parametrize("ok,expected", [
    ("solution.py", "solution.py"),
    ("./solution.py", "solution.py"),
    ("src/solution.py", "src/solution.py"),
])
def test_ordinary_relative_paths_survive(ok, expected):
    assert _safe_relative(ok) == expected


def test_a_tampered_fixture_set_moves_the_claim_digest():
    """Why the new fields are signed rather than excluded. An unsigned fixture
    set lets a republisher swap in a test file with the SAME test ids and
    weakened assertions, which reproduces the canonical hash against a tampered
    candidate and buys a false MATCH outright. Signing them closes that."""
    kw = dict(task_id="t", candidate=CORRECT, oracle="pytest",
              oracle_cmd="python -m pytest tests/", oracle_output_hash="h",
              verdict="PASS", model_ref="stub", seed=0, prompt_hash="p",
              budget_spent={}, candidate_path="solution.py")
    real = ProofEnvelope(**kw, oracle_inputs={
        "tests/t.py": "def test_add():\n    assert add(2, 3) == 5\n"})
    weakened = ProofEnvelope(**kw, oracle_inputs={
        "tests/t.py": "def test_add():\n    assert True\n"})
    assert real.claim_sha256() != weakened.claim_sha256()
    assert real.content_hash() != weakened.content_hash()
    # and both travel in the receipt, or the fallback has nothing to read
    assert json.loads(real.to_json())["oracle_inputs"]
    assert json.loads(real.to_json())["candidate_path"] == "solution.py"
