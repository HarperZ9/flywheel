#!/usr/bin/env python3
"""confirmatory_supervisor.py -- restart the confirmatory walk if it is not running.

Two aborts taught the same lesson from two directions. The first died on session
teardown (DBG_TERMINATE_PROCESS), the second on a console control event
(STATUS_CONTROL_C_EXIT) after the machine had already rebooted underneath the
run. Both were attempts to make the walk unkillable, and both failed, because
this environment periodically resets and a process cannot veto that from inside.

So the mitigation is not immortality, it is cheap recovery. The walker already
skips a pair whose pool index exists, so a restart costs only the pair that was
in flight. This supervisor supplies the restart: run it on a short schedule and
the walk survives any number of resets, finishing across them.

It is idempotent and MECHANICAL. It starts nothing when a walk is already
running or when the journal already carries run_end, and it never reads a
verdict, a candidate, or an outcome. Peeking is a protocol violation under
parent section 7, so the supervisor is built without the ability.

Stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JOURNAL = REPO / "artifacts" / "pool" / "confirmatory-journal.jsonl"
WALKER = REPO / "scripts" / "run_confirmatory.py"
SUPERVISOR_LOG = REPO / "artifacts" / "pool" / "supervisor.jsonl"


def walk_is_running() -> bool:
    """True when a run_confirmatory process is alive. Uses tasklist rather than
    a pidfile: a pidfile written by a process that was killed without cleanup
    is exactly the stale state this has to survive."""
    if sys.platform != "win32":
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True,
                             text=True).stdout
        return "run_confirmatory.py" in out
    ps = ("Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
          "Where-Object { $_.CommandLine -match 'run_confirmatory' } | "
          "Measure-Object | Select-Object -ExpandProperty Count")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip()
    try:
        return int(out or "0") > 0
    except ValueError:
        return False


def walk_is_complete() -> bool:
    """True when the journal carries run_end. Reads ONLY the event name."""
    if not JOURNAL.is_file():
        return False
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("event") == "run_end":
                return True
        except json.JSONDecodeError:
            continue
    return False


def log(record: dict) -> None:
    SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    record["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    if walk_is_complete():
        log({"action": "none", "reason": "run_end already in the journal"})
        return 0
    if walk_is_running():
        log({"action": "none", "reason": "a walk is already running"})
        return 0
    flags = 0
    if sys.platform == "win32":
        flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                 | getattr(subprocess, "DETACHED_PROCESS", 0))
    subprocess.Popen([sys.executable, "-u", str(WALKER)], cwd=str(REPO),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags)
    log({"action": "restarted", "reason": "no walk running and no run_end"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
