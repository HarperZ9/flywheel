"""7.8 stage B1: replay a reproducible task in a hardened shared clone. A
scripted proposer that fixes the failing test gives PASS, one that does not
gives FAIL, and the regression report says which changed; the owner's
repository is unchanged; a drifted clone gives UNREPRODUCIBLE; the gate's
environment holds no planted provider key; a junction inside the clone is
removed as a link; a clone left by a crash is swept at start.

The gate runs only inside the host's sandbox (sandboxed_runner). A host with
no usable sandbox, such as Linux without a bubblewrap the kernel lets start,
gets UNREPRODUCIBLE with SANDBOX_UNAVAILABLE and the gate never runs; the tests
that need a real gate check that refusal there. The verdict and regression
logic is also checked on every host with the gate run by a plain subprocess."""
import os
import shutil
import subprocess
import sys

import pytest

from bench_fixtures import SHOW_ENV, git_repo, plant_run
from delete_fixtures import OWNER
from harness import trace_bench_replay as replay
from harness.trace_bench_tasks import build_tasks
from trace_enc_fakes import StreamTestProvider, using

FAKE_KEY = "sk-" + "proj-" + "f" * 40
FIX = 'TOOL write_file {"path": "calc.py", "content": "def add(a, b):\\n    return a + b\\n"}'


class Scripted:
    def __init__(self, script):
        self.script = list(script)

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        class Out:
            text = self.script.pop(0) if self.script else "done."
            model_ref = "scripted"
            seed = 0
        return Out()


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    with using(StreamTestProvider()):
        yield home, git_repo(tmp_path), tmp_path


def _sandbox_usable() -> bool:
    """The same probe test_sandboxed_runner uses: a backend the kernel lets start."""
    if os.name == "nt":
        return True
    from harness.posix_sandbox import PROGRAM, backend_for
    from harness.sandbox_probe import sandbox_starts
    backend = backend_for()
    return backend is not None and sandbox_starts(
        backend, shutil.which(PROGRAM[backend]) or PROGRAM[backend])


SANDBOX = _sandbox_usable()
UNAVAILABLE = ("UNREPRODUCIBLE", "SANDBOX_UNAVAILABLE")


def _unconfined_gate(clone, gate_cmd):
    done = subprocess.run(gate_cmd, shell=True, cwd=clone, capture_output=True, text=True,
                          timeout=120)
    return done.returncode == 0, done.stdout + done.stderr


def _tree(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
            if p.is_file()}


def _proposers(fixing: set):
    return lambda task, endpoint: Scripted([FIX, "fixed."] if task["goal"] in fixing
                                           else ["no change."])


def _replay_fix_and_no_fix(home, repo):
    plant_run(home, repo, operation="op_" + "1" * 32, goal="fix add", tests_pass=False)
    plant_run(home, repo, operation="op_" + "2" * 32, goal="leave add", tests_pass=True)
    build_tasks(home, OWNER)
    before = _tree(repo)
    report = replay.replay_tasks(home, OWNER, ["ep-one"], proposer_for=_proposers({"fix add"}))
    assert report["classes"] == {"REPRODUCIBLE": 2}
    assert _tree(repo) == before
    assert not any((home / "state" / "trace-bench").rglob("repo"))
    return report


def _assert_fix_passes_and_no_fix_fails(report):
    verdicts = {r["goal_digest"]: r["verdict"] for r in report["results"]}
    assert sorted(verdicts.values()) == ["FAIL", "PASS"]
    regression = report["regression"]
    assert [r["current"] for r in regression["improvements"]] == ["PASS"]
    assert [r["current"] for r in regression["regressions"]] == ["FAIL"]


def test_fix_passes_no_fix_fails_and_the_report_names_the_change(world):
    home, repo, _ = world
    report = _replay_fix_and_no_fix(home, repo)
    if not SANDBOX:
        # The gate never runs unconfined: both tasks say why, and neither
        # claims a verdict the gate did not give.
        assert [(r["verdict"], r["reason"]) for r in report["results"]] == [UNAVAILABLE] * 2
        assert report["regression"]["improvements"] == []
        assert report["regression"]["regressions"] == []
        return
    _assert_fix_passes_and_no_fix_fails(report)


def test_the_verdict_and_regression_logic_holds_on_every_host(world, monkeypatch):
    """The same replay with the gate run by a plain subprocess, so a host with
    no sandbox still checks PASS, FAIL and the regression report."""
    home, repo, _ = world
    monkeypatch.setattr(replay, "_run_gate", _unconfined_gate)
    _assert_fix_passes_and_no_fix_fails(_replay_fix_and_no_fix(home, repo))


def test_a_drifted_clone_is_unreproducible(world, monkeypatch):
    home, repo, _ = world
    plant_run(home, repo, operation="op_" + "3" * 32)
    build_tasks(home, OWNER)
    real = replay._checkout

    def drifted(clone, head):
        real(clone, head)
        (clone / "stray.txt").write_text("not in the recorded tree\n")
    monkeypatch.setattr(replay, "_checkout", drifted)
    report = replay.replay_tasks(home, OWNER, ["ep-one"], proposer_for=_proposers(set()))
    (result,) = report["results"]
    assert result["verdict"] == "UNREPRODUCIBLE" and result["reason"] == "CLONE_DRIFTED"


def test_the_gate_environment_holds_no_provider_key(world):
    home, repo, _ = world
    plant_run(home, repo, operation="op_" + "4" * 32, test_cmd=SHOW_ENV)
    build_tasks(home, OWNER)
    report = replay.replay_tasks(home, OWNER, ["ep-one"], proposer_for=_proposers(set()))
    (result,) = report["results"]
    stored = replay.ReplayResults(home, OWNER).read(result["result_ref"])
    if not SANDBOX:
        # No sandbox, no gate: nothing ran that could see the key, and the
        # stored result carries no gate output.
        assert (result["verdict"], result["reason"]) == UNAVAILABLE
        assert "gate_output" not in stored
        return
    output = stored["gate_output"]
    assert "PATH" in output and FAKE_KEY not in output and "OPENAI_API_KEY" not in output


def _junction(link, target):
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True,
                       capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_junction_in_the_clone_is_removed_as_a_link(world, monkeypatch):
    home, repo, base = world
    outside = base / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("stays\n")
    plant_run(home, repo, operation="op_" + "5" * 32)
    build_tasks(home, OWNER)
    real = replay._run_gate

    def with_link(clone, gate_cmd):
        _junction(clone / "linked", outside)
        return real(clone, gate_cmd)
    monkeypatch.setattr(replay, "_run_gate", with_link)
    replay.replay_tasks(home, OWNER, ["ep-one"], proposer_for=_proposers(set()))
    assert (outside / "keep.txt").read_text() == "stays\n"
    assert not list(replay.replay_root(home, OWNER).iterdir())


def test_a_clone_left_by_a_crash_is_swept_at_start(world):
    home, _, base = world
    outside = base / "outside2"
    outside.mkdir()
    (outside / "keep.txt").write_text("stays\n")
    leftover = replay.replay_root(home, OWNER) / "rpl_crashed"
    (leftover / "repo").mkdir(parents=True)
    (leftover / "repo" / "file.txt").write_text("x")
    _junction(leftover / "repo" / "linked", outside)
    assert replay.sweep(home, OWNER) == 1
    assert not leftover.exists() and (outside / "keep.txt").exists()
