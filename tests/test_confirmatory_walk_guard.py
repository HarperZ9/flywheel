"""run_confirmatory.py's one-walk-at-a-time guard.

Two walkers once ran at once and both aimed at telos-coder-32b. The guard that
prevents a repeat has one subtle requirement: it must see a second walker
WITHOUT seeing the cmd.exe wrapper that launched the first one, whose command
line also names this script. A guard that counts that wrapper refuses every
wrapped launch, which is worse than no guard at all. Both directions are
asserted here.

Loaded the importlib way, since scripts/ is not a package.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "run_confirmatory", ROOT / "scripts" / "run_confirmatory.py")
run_confirmatory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_confirmatory)

SELF = 4242
WALKER_CMD = r"C:\Python312\python.exe -u scripts\run_confirmatory.py"


def test_a_second_walker_is_seen():
    records = [(SELF, "python.exe", WALKER_CMD),
               (9001, "python.exe", WALKER_CMD)]
    assert run_confirmatory.other_walk_pids(records, SELF) == [9001]


def test_self_is_never_counted():
    records = [(SELF, "python.exe", WALKER_CMD)]
    assert run_confirmatory.other_walk_pids(records, SELF) == []


def test_the_cmd_wrapper_that_launched_us_is_not_counted():
    """The exact false positive that would make the guard unusable: our own
    parent, a shell whose command line quotes this script's name."""
    wrapper = (r'"C:\WINDOWS\system32\cmd.EXE" /c cd /d C:\dev\_w && python '
               r"-u scripts\run_confirmatory.py > confirmatory.log 2>&1")
    records = [(SELF, "python.exe", WALKER_CMD), (2832, "cmd.EXE", wrapper)]
    assert run_confirmatory.other_walk_pids(records, SELF) == []


def test_the_supervisor_is_not_a_walk():
    """The supervisor runs on a schedule while the walk runs. If the guard
    counted it, every restart the supervisor performed would be refused."""
    sup = r"C:\Python312\pythonw.exe C:\dev\_w\scripts\confirmatory_supervisor.py"
    records = [(SELF, "python.exe", WALKER_CMD), (777, "pythonw.exe", sup)]
    assert run_confirmatory.other_walk_pids(records, SELF) == []


def test_rows_without_a_command_line_are_skipped():
    records = [(SELF, "python.exe", WALKER_CMD), (5, "python.exe", None),
               (6, "python.exe", "")]
    assert run_confirmatory.other_walk_pids(records, SELF) == []


def _fake_run(stdout=b"", raises=None):
    """Stand in for subprocess.run, and model the REAL failure faithfully.

    When the caller asks for decoded text, a byte the ANSI codepage cannot map
    kills subprocess's reader thread and the CompletedProcess comes back with
    stdout=None. That is what killed the walker, so the fake reproduces it
    rather than a tidier error the real library never raises.
    """
    def run(*args, **kw):
        if raises is not None:
            raise raises
        if kw.get("text") or kw.get("encoding") or kw.get("universal_newlines"):
            return types.SimpleNamespace(stdout=None, stderr=None, returncode=0)
        return types.SimpleNamespace(stdout=stdout, stderr=b"", returncode=0)
    return run


@pytest.mark.parametrize("platform,blob", [
    ("win32",
     b"4242|@|python.exe|@|C:\\gr\x81n\\python.exe -u scripts\\run_confirmatory.py\r\n"
     b"7|@|cmd.exe|@|unrelated\r\n"),
    ("linux",
     b"4242 python /gr\x81n/python -u scripts/run_confirmatory.py\n"
     b"7 sh unrelated\n"),
])
def test_an_undecodable_command_line_does_not_kill_the_walker(
        monkeypatch, platform, blob):
    """The byte 0x81 is undefined in cp1252 and appears in OEM output for a
    u with an umlaut. One unrelated process carrying one anywhere on the machine
    used to end the walk at startup, before it journaled anything, while the
    supervisor kept recording restarts that had never run.

    Parametrized over BOTH platform branches after the first version fed the
    Windows separator format to whatever branch the host happened to take: it
    passed on the machine it was written on and failed on every CI runner,
    which is the same shape of coupling as the bug it guards against.
    """
    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr(run_confirmatory.subprocess, "run", _fake_run(blob))
    records = run_confirmatory._live_process_records()
    assert [r[0] for r in records] == [4242, 7]
    assert run_confirmatory.other_walk_pids(records, 1) == [4242]


def test_a_scan_that_cannot_run_fails_open(monkeypatch):
    """The docstring promises a failed scan blocks nothing. A guard that
    refuses every launch because a process query was unavailable would stop the
    pass as surely as the bug it prevents."""
    for boom in (FileNotFoundError("powershell.exe"),
                 OSError("handle is invalid"),
                 subprocess.TimeoutExpired(cmd="powershell.exe", timeout=30.0)):
        monkeypatch.setattr(run_confirmatory.subprocess, "run",
                            _fake_run(raises=boom))
        assert run_confirmatory._live_process_records() == []


def test_the_scan_is_bounded_in_time(monkeypatch):
    """A wedged process query would hang the walker forever, and the hung
    walker still matches the supervisor's liveness probe, so the self-healing
    restart would never fire."""
    seen = {}
    def run(*args, **kw):
        seen.update(kw)
        return types.SimpleNamespace(stdout=b"", stderr=b"", returncode=0)
    monkeypatch.setattr(run_confirmatory.subprocess, "run", run)
    run_confirmatory._live_process_records()
    assert seen.get("timeout"), "the process scan was launched without a timeout"


def test_the_live_scan_actually_reads_this_platform():
    """Non-vacuity for the OS query itself. A predicate that is perfect over
    synthetic rows proves nothing if the real scan returns an empty list on
    this platform, so this asserts the scan finds the running interpreter."""
    records = run_confirmatory._live_process_records()
    assert records, "the process scan returned no rows at all"
    me = [r for r in records if r[0] == os.getpid()]
    assert me, f"the scan did not find our own pid {os.getpid()}"
    assert "python" in me[0][1].lower(), me[0]
