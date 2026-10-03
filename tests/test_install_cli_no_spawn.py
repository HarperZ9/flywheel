"""`flywheel install` with help or a bad argument starts no process at all.

test_install_cli_strict replaces install_lane. Here the fake sits one level
lower, at the package manager itself: subprocess.run and subprocess.Popen record
and refuse. Help and every bad argument must leave both untouched and write no
registry. The control runs the same command line with an argument that parses
and shows the recorder does see the pip call, as ``<this python> -m pip``.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

import harness.lanes as ln
from harness import cli_entry
from harness.lanes_registry import LANES


@pytest.fixture
def spawns(tmp_path, monkeypatch):
    seen: list = []

    def record(args, *rest, **kwargs):
        seen.append(list(args) if not isinstance(args, str) else args)
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    def refuse_popen(args, *rest, **kwargs):
        seen.append(list(args) if not isinstance(args, str) else args)
        raise OSError("the package manager must not start")

    monkeypatch.setattr(subprocess, "run", record)
    monkeypatch.setattr(subprocess, "Popen", refuse_popen)
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    return seen, tmp_path / "lanes.json"


@pytest.mark.parametrize("argv", [
    ["--help"], ["-h"], ["--lanes", "gather", "--help"], ["--bogus"], ["gather"],
    ["--lanes"], ["--profile"], ["--profile", "bogus"], ["--lanes=gather", "extra"],
    ["--lanes", "no-such-lane"], ["--lanes", "gather", "--lanes", "index"], ["--"],
    ["--LANES", "gather"], ["--lanes", "all,gather"]])
def test_help_or_a_bad_argument_starts_no_package_manager(argv, spawns, capsys):
    seen, registry = spawns
    wants_help = any(arg in ("-h", "--help") for arg in argv)
    assert cli_entry.main(["install", *argv]) == (0 if wants_help else 2)
    assert seen == [], f"install {argv} started {seen}"
    assert not registry.exists(), "nothing may be recorded when nothing installed"
    printed = capsys.readouterr()
    assert "usage: flywheel install" in (printed.out if wants_help else printed.err)


def test_control_an_argument_that_parses_reaches_pip_under_this_python(spawns):
    seen, registry = spawns
    assert cli_entry.main(["install", "--lanes", "gather"]) == 0
    lane = LANES["gather"]
    assert seen == [[sys.executable, "-m", "pip", "install",
                     f"{lane.install_name}=={lane.version}"]]
    assert registry.exists()
