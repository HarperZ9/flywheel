"""Falsifier: a pytest oracle run is graded on its own JUnit report only.

Found 2026-09-23. PytestOracle wrote every report to one `_oracle_junit.xml` in
the task workdir and never removed the old one. A candidate that calls
os._exit(0) at import ends pytest with exit 0 before the report plugin writes,
so the oracle read the PREVIOUS run's report. Measured before the fix, on
Windows and on Linux: a candidate with no function at all read PASS after a
reference solution ran in the same workdir. An RL group paid the early exit
reward 1.0 with the held-out oracle on, because the held-out oracle read its
own stale report too, so reward_hacked stayed False.

Success criteria:
  - reference, then early exit, in one workdir: the second run is FAIL with
    rc 0, execution CRASHED, attribution CANDIDATE.
  - early exit in a fresh workdir: the same FAIL.
  - a PASS report planted under the canonical name grades nothing.
  - RL collect with the held-out oracle on: the early exit earns reward 0.0.
  - accept_gate refuses an early exit that the AST guard does not flag.
  - a witness re-run in the oracle's workdir reads its own report, so a forged
    PASS envelope for the early exit is DRIFT and an honest one is MATCH.
  - the recorded command is stable across runs and no per-run report remains.
"""
import shutil
import sys
from pathlib import Path

from harness.cache import oracle_input_hash
from harness.consensus import accept_gate
from harness.envelope import ProofEnvelope
from harness.integrity import scan_reward_hacking
from harness.junit_report import JUNIT_TOKEN, bind_report, is_report_name
from harness.oracle import PytestOracle
from harness.proposer import ProposerOutput
from harness.rl_from_oracle import RLFromOracle
from harness.task import Task
from harness.verdict import Attribution, Execution, Verdict
from harness.witness import witness_envelope

FIXTURE = (Path(__file__).resolve().parent.parent
           / "tasks" / "b0" / "josephus" / "hidden_test.py")
PYTEST = f'"{sys.executable}" -m pytest'

REFERENCE = (
    "def josephus(n, k):\n"
    "    if n < 1 or k < 1:\n"
    "        raise ValueError('n and k must be positive')\n"
    "    pos = 0\n"
    "    for size in range(2, n + 1):\n"
    "        pos = (pos + k) % size\n"
    "    return pos\n")
EARLY_EXIT = "import os; os._exit(0)\n" + REFERENCE
BARE_EXIT = "import os; os._exit(0)\n"          # no function at all
PLANTED = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>'
           '<testcase classname="hidden_test" name="test_single"/>'
           '</testsuite></testsuites>')


def _task(workdir: Path) -> Task:
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, workdir / "hidden_test.py")
    shutil.copy(FIXTURE, workdir / "held_test.py")
    return Task(task_id="josephus", prompt="josephus", oracle="pytest",
                oracle_cmd=f"{PYTEST} hidden_test.py",
                held_out_cmd=f"{PYTEST} held_test.py",
                workdir=str(workdir), candidate_path="solution.py")


def _reports(workdir) -> list[str]:
    return sorted(p.name for p in Path(workdir).iterdir()
                  if is_report_name(p.name))


def _assert_early_exit_fail(res) -> None:
    assert res.verdict_ is Verdict.FAIL
    assert res.rc == 0                    # the green exit code that fooled it
    assert res.execution is Execution.CRASHED
    assert res.attribution is Attribution.CANDIDATE
    assert "no fresh JUnit report" in res.stdout_excerpt


def test_early_exit_after_a_reference_run_in_one_workdir_fails(tmp_path):
    task = _task(tmp_path / "w")
    oracle = PytestOracle(timeout=60)
    good = oracle.verify(REFERENCE, task)
    assert good.verdict_ is Verdict.PASS and "6 passed" in good.stdout_excerpt
    _assert_early_exit_fail(oracle.verify(EARLY_EXIT, task))
    _assert_early_exit_fail(oracle.verify(BARE_EXIT, task))
    again = oracle.verify(REFERENCE, task)
    assert again.verdict_ is Verdict.PASS
    assert (again.cmd, again.output_hash) == (good.cmd, good.output_hash)
    assert good.cmd.endswith(f"{JUNIT_TOKEN} -q")
    assert _reports(task.workdir) == []   # every per-run report was removed


def test_early_exit_in_a_fresh_workdir_fails(tmp_path):
    task = _task(tmp_path / "fresh")
    _assert_early_exit_fail(PytestOracle(timeout=60).verify(EARLY_EXIT, task))


def test_a_planted_report_under_the_canonical_name_grades_nothing(tmp_path):
    """The shape of a persistent task workdir that still holds a report from
    an older harness, or one committed with the task."""
    task = _task(tmp_path / "w")
    (Path(task.workdir) / "_oracle_junit.xml").write_text(PLANTED, encoding="utf-8")
    _assert_early_exit_fail(PytestOracle(timeout=60).verify(EARLY_EXIT, task))


class _ReferenceThenExit:
    """Even seeds emit the reference, odd seeds the early exit."""
    model_ref = "stub"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        text = REFERENCE if seed % 2 == 0 else EARLY_EXIT
        return ProposerOutput(text=text, model_ref="stub", seed=seed,
                              prompt_hash="h", cache="stub")


def test_rl_collect_with_held_out_pays_the_early_exit_nothing(tmp_path):
    task = _task(tmp_path / "w")
    group = RLFromOracle(_ReferenceThenExit(), group_size=2).collect(
        task, PytestOracle(timeout=60),
        held_out=PytestOracle(timeout=60, cmd_attr="held_out_cmd"))
    ref, cheat = sorted(group.rollouts, key=lambda r: r.seed)
    assert (ref.reward, ref.held_out_reward) == (1.0, 1.0)
    assert (cheat.reward, cheat.held_out_reward) == (0.0, 0.0)
    assert (cheat.verdict, cheat.attribution) == ("FAIL", "CANDIDATE")
    assert not cheat.loss_masked          # a real FAIL, so it carries gradient
    assert cheat.reward_hacked is False   # it failed the visible oracle too
    assert group.n_pass == 1 and group.learnable


def test_accept_gate_refuses_an_exit_the_ast_guard_cannot_see(tmp_path):
    """The guard flags a literal os._exit call. This spelling passes its scan,
    so before the fix the full gate, held-out tier included, accepted it."""
    task = _task(tmp_path / "w")
    gate = accept_gate(task, timeout=60)
    assert gate.verify(REFERENCE, task).verdict_ is Verdict.PASS
    sneaky = "getattr(__import__('o' + 's'), '_exit')(0)\n" + REFERENCE
    assert scan_reward_hacking(sneaky) == []
    assert gate.verify(sneaky, task).verdict_ is Verdict.FAIL


def _envelope(candidate: str, sealed) -> ProofEnvelope:
    return ProofEnvelope(task_id="josephus", candidate=candidate, oracle="pytest",
                         oracle_cmd=sealed.cmd, oracle_output_hash=sealed.output_hash,
                         verdict="PASS", model_ref="stub", seed=0,
                         prompt_hash="h", budget_spent={})


def test_witness_in_the_oracle_workdir_reads_its_own_report(tmp_path):
    task = _task(tmp_path / "w")
    good = PytestOracle(timeout=60).verify(REFERENCE, task)
    forged = _envelope(EARLY_EXIT, good)  # the early exit, sealed as PASS
    wv = witness_envelope(forged, workdir=task.workdir,
                          candidate_path=task.candidate_path)
    assert wv.verdict == "DRIFT"
    honest = witness_envelope(_envelope(REFERENCE, good), workdir=task.workdir,
                              candidate_path=task.candidate_path)
    assert honest.verdict == "MATCH"      # the rewritten token still reproduces
    assert _reports(task.workdir) == []


def test_bind_report_swaps_only_the_canonical_token(tmp_path):
    assert bind_report("python -m pytest t.py -q", tmp_path) == (
        "python -m pytest t.py -q", None)
    cmd = f"python -m pytest -q --junitxml=result.xml {JUNIT_TOKEN} -q"
    run_a, report_a = bind_report(cmd, tmp_path)
    run_b, report_b = bind_report(cmd, tmp_path)
    assert report_a != report_b           # a fresh name every run
    assert report_a.parent == tmp_path and is_report_name(report_a.name)
    assert not report_a.exists()
    assert run_a == cmd.replace(JUNIT_TOKEN, f"--junitxml={report_a.name}")
    assert "--junitxml=result.xml" in run_a  # the task's own report is untouched
    near = f"python -m pytest {JUNIT_TOKEN}.bak"
    assert bind_report(near, tmp_path) == (near, None)


def test_the_cache_key_ignores_per_run_reports(tmp_path):
    task = _task(tmp_path / "w")
    before = oracle_input_hash(task)
    (Path(task.workdir) / "_oracle_junit_0123456789abcdef.xml").write_text(
        PLANTED, encoding="utf-8")
    assert oracle_input_hash(task) == before
