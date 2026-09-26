"""7.8 stage B1: replay a reproducible task in a hardened shared clone. A
scripted proposer that fixes the failing test gives PASS, one that does not
gives FAIL, and the regression report says which changed; the owner's
repository is unchanged; a drifted clone gives UNREPRODUCIBLE; the gate's
environment holds no planted provider key; a junction inside the clone is
removed as a link; a clone left by a crash is swept at start."""
import os
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


def _tree(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
            if p.is_file()}


def _proposers(fixing: set):
    return lambda task, endpoint: Scripted([FIX, "fixed."] if task["goal"] in fixing
                                           else ["no change."])


def test_fix_passes_no_fix_fails_and_the_report_names_the_change(world):
    home, repo, _ = world
    plant_run(home, repo, operation="op_" + "1" * 32, goal="fix add", tests_pass=False)
    plant_run(home, repo, operation="op_" + "2" * 32, goal="leave add", tests_pass=True)
    build_tasks(home, OWNER)
    before = _tree(repo)
    report = replay.replay_tasks(home, OWNER, ["ep-one"], proposer_for=_proposers({"fix add"}))
    verdicts = {r["goal_digest"]: r["verdict"] for r in report["results"]}
    assert sorted(verdicts.values()) == ["FAIL", "PASS"]
    regression = report["regression"]
    assert [r["current"] for r in regression["improvements"]] == ["PASS"]
    assert [r["current"] for r in regression["regressions"]] == ["FAIL"]
    assert report["classes"] == {"REPRODUCIBLE": 2}
    assert _tree(repo) == before
    assert not any((home / "state" / "trace-bench").rglob("repo"))


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
    output = replay.ReplayResults(home, OWNER).read(result["result_ref"])["gate_output"]
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
