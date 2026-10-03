"""`flywheel install` starts the package manager it means to, never a planted one.

1.1.0 ran ``["pip", ...]`` and ``["npm", ...]`` by bare name. pip then came from
whatever was first on PATH, or from the working folder on Windows, instead of
the interpreter the lane launches with, and npm failed on Windows because it is
``npm.cmd``. Every test here fakes the package manager: subprocess.run is
replaced, or the npm on PATH is a script that only records its arguments.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import harness.lanes as ln
from harness.lanes_registry import LANES

WINDOWS = os.name == "nt"
NO_CWD = "NoDefaultCurrentDirectoryInExePath"
PIP_LANE = "gather"
NPM_LANE = "learn"


def same(a, b) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def fake_program(folder: Path, name: str, record: Path) -> Path:
    """``name`` in ``folder``: records its arguments in ``record`` and exits 0."""
    folder.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        path = folder / (name if name.endswith(".exe") else f"{name}.cmd")
        if name.endswith(".exe"):
            path.write_bytes(b"MZ")  # found by a lookup; never started by these tests
        else:
            path.write_text(f'@echo %*> "{record}"\r\n', encoding="utf-8")
    else:
        path = folder / name
        path.write_text(f'#!/bin/sh\necho "$@" > "{record}"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


@pytest.fixture
def work(tmp_path, monkeypatch):
    """The caller's working folder, holding a planted pip and npm."""
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.chdir(folder)
    monkeypatch.delenv(NO_CWD, raising=False)
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    fake_program(folder, "pip.exe" if WINDOWS else "pip", tmp_path / "planted-pip.txt")
    fake_program(folder, "npm", tmp_path / "planted-npm.txt")
    return folder


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(cmd, *args, **kwargs):
        seen.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_pip_runs_as_this_interpreter_and_never_a_pip_on_path(work, calls, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", os.pathsep.join((".", str(tmp_path / "work"))))
    result = ln.install_lane(PIP_LANE, profile="package")
    assert result["installed"] is True
    ((cmd, kwargs),) = calls
    assert cmd == [sys.executable, "-m", "pip", "install",
                   f"{LANES[PIP_LANE].install_name}=={LANES[PIP_LANE].version}"]
    folder = Path(kwargs["cwd"])
    assert not same(folder, work), "pip must not run where a planted pip package sits"
    assert not (tmp_path / "planted-pip.txt").exists()


def test_a_source_install_is_editable_through_the_same_interpreter(work, calls, tmp_path, monkeypatch):
    source = tmp_path / "gather-src"
    source.mkdir()
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    assert ln.install_lane(PIP_LANE, profile="source")["installed"] is True
    ((cmd, _kwargs),) = calls
    assert cmd == [sys.executable, "-m", "pip", "install", "-e", str(source)]


def test_a_pinned_runtime_python_is_the_interpreter_pip_runs_under(work, calls, tmp_path):
    pinned = tmp_path / "py" / ("python.exe" if WINDOWS else "python")
    pinned.parent.mkdir()
    pinned.write_bytes(b"")
    (tmp_path / "lanes.json").write_text(
        json.dumps({PIP_LANE: {"runtime_python": str(pinned)}}), encoding="utf-8")
    assert ln.install_lane(PIP_LANE, profile="package")["installed"] is True
    ((cmd, _kwargs),) = calls
    assert same(cmd[0], pinned) and cmd[1:3] == ["-m", "pip"]


def test_a_frozen_build_without_an_interpreter_refuses_pip(work, calls, monkeypatch):
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    result = ln.install_lane(PIP_LANE, profile="package")
    assert result["installed"] is False
    assert result["code"] == "pip_interpreter_unavailable"
    assert calls == []


def test_npm_resolves_from_a_safe_path_folder_past_a_plant(work, calls, tmp_path, monkeypatch):
    real = fake_program(tmp_path / "bin", "npm", tmp_path / "npm.txt")
    monkeypatch.setenv("PATH", os.pathsep.join((".", str(tmp_path / "bin"))))
    assert ln.install_lane(NPM_LANE, profile="package")["installed"] is True
    ((cmd, kwargs),) = calls
    assert same(cmd[0], real)
    assert cmd[1:] == ["install", "-g", f"{LANES[NPM_LANE].install_name}@{LANES[NPM_LANE].version}"]
    assert not same(kwargs["cwd"], work)


def test_no_safe_npm_is_a_typed_refusal_and_nothing_starts(work, calls, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", os.pathsep.join((".", str(empty))))
    result = ln.install_lane(NPM_LANE, profile="package")
    assert result["installed"] is False
    assert result["code"] == "npm_unavailable"
    assert "npm" in result["detail"] and str(tmp_path) not in result["detail"]
    assert calls == []


def test_the_resolved_npm_really_starts(work, tmp_path, monkeypatch):
    """No subprocess fake: a recording npm on PATH is started for real. On
    Windows 1.1.0 failed here with WinError 2, because npm is npm.cmd."""
    record = tmp_path / "npm-args.txt"
    fake_program(tmp_path / "bin", "npm", record)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    result = ln.install_lane(NPM_LANE, profile="package")
    assert result["installed"] is True, result
    spec = f"{LANES[NPM_LANE].install_name}@{LANES[NPM_LANE].version}"
    assert record.read_text(encoding="utf-8").split() == ["install", "-g", spec]
    assert not (tmp_path / "planted-npm.txt").exists()
