"""No Lean child process inherits the harness's environment.

A candidate proof runs code while Lean elaborates it, and
`#eval IO.getEnv "NAME"` prints any variable the Lean process holds into the
output a receipt keeps. Every Lean spawn therefore starts from
`harness.lean_env.lean_env()`, an allow-list.

Each test sets a canary variable in this process and looks at the
environment the child is given:

  a real child      the Python interpreter stands in for Lean and prints its
                    own environment, started through the same spawn helper
  each spawn site   the spawn call is replaced by one that records the `env`
                    it was handed, and the site's own function is run
  the source        no Lean module copies `os.environ` for a child, and every
                    direct `subprocess` call in them passes `env=`
  a real toolchain  where `lean` is installed, a file that evaluates
                    `IO.getEnv` on the canary prints `none`
"""
import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness import lean_env, lean_export, lean_replay, lean_sandbox, proof_run
from harness.infra import lean_adapter

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

CANARY = "FLYWHEEL_TEST_CANARY_VARIABLE"
VALUE = "canary-value-that-must-not-reach-a-lean-child"
HARNESS = Path(lean_env.__file__).parent
LEAN_MODULES = sorted([*HARNESS.glob("lean_*.py"), HARNESS / "proof_run.py",
                       HARNESS / "infra" / "lean_adapter.py"])


@pytest.fixture
def canary(monkeypatch):
    monkeypatch.setenv(CANARY, VALUE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("LEAN_NUM_THREADS", "2")


def _clean(env) -> None:
    assert isinstance(env, dict), "the child is given an explicit environment"
    assert CANARY not in env and "ANTHROPIC_API_KEY" not in env
    assert VALUE not in json.dumps(env)
    assert "PATH" in {name.upper() for name in env}, "control: the child can still start"


def test_the_allow_list_drops_the_canary_and_keeps_what_lean_needs(canary):
    env = lean_env.lean_env()
    _clean(env)
    assert env["LEAN_NUM_THREADS"] == "2"
    assert lean_env.lean_env({"Path": "x", CANARY: VALUE, "http_proxy": "u:p@h"}) == {"Path": "x"}


def test_control_the_parent_does_hold_the_canary(canary):
    assert os.environ[CANARY] == VALUE


@pytest.mark.parametrize("given", [None, "copy"])
def test_a_real_child_started_by_the_lean_spawn_helper_has_no_canary(canary, given):
    env = None if given is None else dict(os.environ)
    code, out = lean_replay.run_killable(
        [sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
        timeout=30, env=env, stderr=subprocess.DEVNULL)
    assert code == 0
    _clean(json.loads(out))


class _Seen:
    """Stands in for a spawn call and records the environment it was handed."""

    def __init__(self):
        self.envs = []

    def run(self, command, *args, **kwargs):
        self.envs.append(kwargs.get("env"))
        return subprocess.CompletedProcess(command, 0, "Lean (version 4.0.0)", "")


def test_site_proof_run(canary, monkeypatch, tmp_path):
    seen = _Seen()
    monkeypatch.setattr(proof_run.subprocess, "run", seen.run)
    source = tmp_path / "x.lean"
    source.write_text("theorem t : True := trivial\n", encoding="utf-8")
    proof_run.run_proof(source, lean=sys.executable)    # any program that exists
    assert len(seen.envs) == 2, "the version probe and the check"
    for env in seen.envs:
        _clean(env)


def test_site_infra_lean_adapter(canary, monkeypatch, tmp_path):
    seen = _Seen()
    monkeypatch.setattr(lean_adapter.subprocess, "run", seen.run)
    # Stand in for the PATH lookup, so the site is reached where no Lean is installed.
    # It hands back the parent's whole environment, which the site must still filter.
    monkeypatch.setattr(lean_adapter.safe_program, "launch",
                        lambda command, **kwargs: (list(command), dict(os.environ)))
    lean_adapter.reset_lean_probe()
    try:
        assert lean_adapter.lean_version()
        source = tmp_path / "x.lean"
        source.write_text("theorem t : True := trivial\n", encoding="utf-8")
        lean_adapter.check_lean_file(source)
    finally:
        lean_adapter.reset_lean_probe()
    assert len(seen.envs) == 2, "the version probe and the check"
    for env in seen.envs:
        _clean(env)


def test_site_lean_export(canary, monkeypatch):
    from harness import safe_program
    seen = _Seen()
    monkeypatch.setattr(subprocess, "run", seen.run)
    monkeypatch.setattr(safe_program, "which", lambda name: name)
    lean_export.lean_axioms("theorem t : True := trivial\n")
    assert len(seen.envs) == 1
    _clean(seen.envs[0])


@pytest.mark.skipif(os.name != "nt", reason="the Windows sandbox path")
def test_site_windows_sandbox(canary, monkeypatch, tmp_path):
    from harness import lean_sandbox_win
    seen = []

    def run(argv, **kwargs):
        seen.append(kwargs["env"])
        raise OSError("stopped by the test after the environment was read")
    monkeypatch.setattr(lean_sandbox_win, "run", run)
    lean_sandbox._run_windows(["lean"], tmp_path, tmp_path, 5, None, {})
    _clean(seen[0])


_WITH_ENV = ("subprocess.run", "subprocess.Popen", "subprocess.check_output",
             "subprocess.call", "subprocess.check_call", "spawn_killable",
             "lean_replay.spawn_killable")
_NO_ENV = ("os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput")


def _spawn_problems(name: str, text: str) -> list:
    """What in one module's source starts a child outside the allow-list.

    A call that takes `env=` must pass one built by `lean_env`. A call that
    cannot take an environment (`os.system`, `os.popen`, `os.spawn*`,
    `os.exec*`, `subprocess.getoutput`) always inherits the parent's, so it is
    a problem wherever it appears."""
    problems = []
    for bad in ("dict(os.environ)", "**os.environ", "env=os.environ", "os.environ.copy()"):
        if bad in text:
            problems.append(f"{name}: {bad}")
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        called = ast.unparse(node.func)
        if called in _NO_ENV or called.startswith(("os.spawn", "os.exec")):
            problems.append(f"{name}:{node.lineno}: {called} cannot take an environment")
        elif called in _WITH_ENV:
            env = next((k.value for k in node.keywords if k.arg == "env"), None)
            if env is None or "lean_env" not in ast.unparse(env):
                problems.append(f"{name}:{node.lineno}: a spawn without lean_env")
    return problems


def test_no_lean_module_copies_the_parent_environment_for_a_child():
    """Every spawn in the Lean modules goes through the allow-list.

    `run_killable` applies it to whatever it is handed, so its callers are
    covered there. A direct `subprocess` call must pass `env=`, and no module
    may build an environment from `dict(os.environ)` or `{**os.environ}`."""
    problems = []
    for path in LEAN_MODULES:
        if path.name != "lean_env.py":
            problems += _spawn_problems(path.name, path.read_text(encoding="utf-8"))
    assert problems == []
    spawn = (HARNESS / "lean_replay.py").read_text(encoding="utf-8")
    assert "spawn_killable(argv, env=lean_env(env)" in spawn


@pytest.mark.parametrize("line", [
    "subprocess.call(['lean', 'x.lean'])",
    "subprocess.check_call(['lean', 'x.lean'], env=dict(PATH='x'))",
    "os.system('lean x.lean')",
    "os.popen('lean x.lean')",
    "os.spawnv(os.P_WAIT, 'lean', ['lean'])",
    "subprocess.getoutput('lean --version')",
    "spawn_killable(['lean'], env=env)",
    "subprocess.run(['lean'])",
])
def test_the_scan_catches_every_way_to_start_a_child(line):
    """The scan once knew `run`, `Popen` and `check_output` only."""
    found = _spawn_problems("planted.py", f"import os, subprocess\n{line}\n")
    assert len(found) == 1 and found[0].startswith("planted.py:2: ")


def test_control_the_scan_passes_a_spawn_that_uses_the_allow_list():
    for line in ("subprocess.call(['lean'], env=lean_env())",
                 "spawn_killable(argv, env=lean_env(env), timeout=5)"):
        assert _spawn_problems("ok.py", line + "\n") == []


@pytest.mark.skipif(shutil.which("lean") is None, reason="no Lean toolchain installed")
def test_a_real_lean_process_cannot_read_the_canary(canary, tmp_path):
    source = tmp_path / "Canary.lean"
    source.write_text(f'#eval IO.getEnv "{CANARY}"\n#eval IO.getEnv "LEAN_NUM_THREADS"\n',
                      encoding="utf-8")
    code, out = lean_replay.run_killable([shutil.which("lean"), str(source)], timeout=55)
    assert code == 0, out
    assert VALUE not in out and "none" in out
    assert 'some "2"' in out, "control: an allow-listed variable is readable"
