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
import sys
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


def test_the_live_scan_actually_reads_this_platform():
    """Non-vacuity for the OS query itself. A predicate that is perfect over
    synthetic rows proves nothing if the real scan returns an empty list on
    this platform, so this asserts the scan finds the running interpreter."""
    records = run_confirmatory._live_process_records()
    assert records, "the process scan returned no rows at all"
    me = [r for r in records if r[0] == os.getpid()]
    assert me, f"the scan did not find our own pid {os.getpid()}"
    assert "python" in me[0][1].lower(), me[0]
