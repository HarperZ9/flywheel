#!/usr/bin/env python3
"""run_confirmatory.py -- the one confirmatory pass, all rungs, both families.

Section 7 of the frozen preregistration allows ONE confirmatory run: no interim
analysis, no peeking at outcomes, no extension on an unfavourable result. A run
aborted for a mechanical reason is logged with its reason, and the rerun is a
NEW prereg hash citing the aborted one.

So this driver does two things and no more. It walks every (family, rung) pair
in a fixed order and calls the fill driver once per pair, and it writes a
progress journal recording, per pair, only MECHANICAL facts: started, finished,
exit code, wall seconds. It never reads a verdict, never counts a pass, never
aggregates an outcome. Peeking is a protocol violation, so the tool that runs
the pass is built unable to peek.

A failing pair does not stop the walk: the remaining pairs are independent
generation work, and stopping early would leave a partial pool that no arm can
be computed from. Every failure is journaled with its exit code so the abort
reason survives for the addendum the stopping rule would require.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Fixed order, written out rather than derived, so a later run cannot quietly
# reorder or drop one. Rung names come from the frozen prereg via rung_pins in
# run_demo_pool.py; these are the served tags for the nine rungs.
RUNGS = [
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2.5:7b",
    "olmo2:7b",
    "telos-coder-14b",
    "qwen2.5-coder:14b-instruct-q4_K_M",
    "telos-coder-32b",
    "qwen2.5-coder:32b-instruct-q4_K_M",
]
FAMILIES = ["zarankiewicz", "rectilinear_crossing"]


# -- one walk at a time -------------------------------------------------------
# Each interruption was recovered by a fresh manual launch, and on 2026-07-28
# two of those launches overlapped. Both skipped the seven finished pairs, then
# both began generating telos-coder-32b into the same pool directory. Two 32B
# generators on one 24 GB card forced a 20% CPU offload and neither wrote a
# candidate in forty-eight minutes. Nothing reached the pool, but the pass had
# two generators aimed at one pair, which is not the single pass section 7
# allows. The supervisor already refused to add a walk while one was alive; a
# hand-typed launch bypassed that check because the walker itself had none.
#
# So the walker refuses to be the second one. It reads live command lines
# rather than a pidfile, for the reason the supervisor does: a pidfile left
# behind by a killed process is precisely the stale state this must survive.
_SEP = "|@|"
_SCAN_TIMEOUT = 30.0


def other_walk_pids(records, self_pid: int) -> list:
    """PIDs of OTHER live walkers, from (pid, image name, command line) rows.

    Two exclusions carry the correctness. Self, obviously. And any process
    whose image is not a Python interpreter: a launch wrapped as
    `cmd /c python -u scripts/run_confirmatory.py > log` gives that cmd.exe a
    command line containing this script's name, so counting it would make the
    guard refuse every wrapped launch by pointing at the caller's own parent.
    """
    pids = []
    for pid, name, cmdline in records:
        if pid == self_pid or not cmdline:
            continue
        if "python" not in (name or "").lower():
            continue
        if "run_confirmatory" in cmdline:
            pids.append(pid)
    return sorted(pids)


def _live_process_records() -> list:
    """(pid, image name, command line) for every live process.

    FAIL OPEN, in the code and not only in this docstring. The first version of
    this function promised that and did not deliver it. It passed `text=True`,
    so Python decoded the pipe with the ANSI codepage while PowerShell writes a
    redirected pipe in the OEM one. One unrelated process ANYWHERE on the
    machine carrying a non-ASCII character in its command line was enough: the
    reader thread raised UnicodeDecodeError, `.stdout` came back None, and the
    walker died at startup BEFORE journaling anything, while the supervisor went
    on recording restarts that had never run. A guard that fails while looking
    like progress is the exact shape of the failure this file exists to prevent.

    So the bytes are decoded lossily on purpose, because the only things ever
    matched here are the ASCII substrings "python" and "run_confirmatory" and an
    ASCII pid, and any scan that fails at all returns nothing.
    """
    if sys.platform == "win32":
        ps = ("Get-CimInstance Win32_Process | ForEach-Object { "
              f"'{{0}}{_SEP}{{1}}{_SEP}{{2}}' -f "
              "$_.ProcessId, $_.Name, $_.CommandLine }")
        cmd = ["powershell.exe", "-NoProfile", "-Command", ps]
    else:
        cmd = ["ps", "-eo", "pid=,comm=,args="]
    try:
        # No text=, no encoding=: decoding is ours to do safely below. The
        # timeout bounds a wedged process query, which would otherwise hang the
        # walker forever while still matching the supervisor's liveness probe.
        proc = subprocess.run(cmd, capture_output=True, timeout=_SCAN_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return []
    out = (proc.stdout or b"").decode("utf-8", "replace")
    records = []
    for line in out.splitlines():
        parts = (line.split(_SEP, 2) if sys.platform == "win32"
                 else line.split(None, 2))
        if len(parts) != 3 or not parts[0].strip().isdigit():
            continue
        records.append((int(parts[0].strip()), parts[1].strip(), parts[2]))
    return records


def journal_append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _rung_dir(out: str, family: str, rung: str) -> Path:
    # run_demo_pool sanitizes the colon in a rung tag for Windows paths.
    return REPO / out / family / rung.replace(":", "_")


def already_done(out: str, family: str, rung: str) -> bool:
    """A pair is complete when its pool index exists. MECHANICAL only: this
    reads whether a file is present, never what any candidate scored. The
    aborted first pass cost eleven pairs that had to restart from nothing;
    resumption bounds a future interruption to the pair in flight."""
    return (_rung_dir(out, family, rung) / "pool_index.json").is_file()


def run_pair(family: str, rung: str, out: str) -> tuple[int, float]:
    cmd = [sys.executable, str(REPO / "scripts" / "run_demo_pool.py"),
           "--confirmatory", "--family", family, "--rung", rung, "--out", out]
    start = time.time()
    # CREATE_NEW_PROCESS_GROUP so a console Ctrl+C/Ctrl+Break aimed at whatever
    # launched us does not propagate into a generation in flight, and
    # CREATE_NO_WINDOW so no console is allocated for it to be aimed at. The
    # first abort was DBG_TERMINATE_PROCESS on session teardown; the second was
    # STATUS_CONTROL_C_EXIT. Neither is fully preventable from inside the
    # process, which is why resumption, not immortality, is the real mitigation.
    flags = 0
    if sys.platform == "win32":
        flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                          creationflags=flags)
    return proc.returncode, round(time.time() - start, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="artifacts/pool")
    ap.add_argument("--journal", default="artifacts/pool/confirmatory-journal.jsonl")
    args = ap.parse_args()

    others = other_walk_pids(_live_process_records(), os.getpid())
    if others:
        print("refusing to start: a confirmatory walk is already running "
              f"(pid {', '.join(str(p) for p in others)}). Two walkers skip "
              "the same finished pairs and then generate the same pair into "
              "the same pool directory.", file=sys.stderr)
        return 3

    journal = REPO / args.journal
    journal_append(journal, {"event": "run_start", "pairs": len(FAMILIES) * len(RUNGS)})
    failures = 0
    for family in FAMILIES:
        for rung in RUNGS:
            if already_done(args.out, family, rung):
                journal_append(journal, {"event": "pair_skipped_complete",
                                         "family": family, "rung": rung})
                print(f"{family} @ {rung}: already complete, skipped",
                      flush=True)
                continue
            journal_append(journal, {"event": "pair_start", "family": family,
                                     "rung": rung})
            code, secs = run_pair(family, rung, args.out)
            if code != 0:
                failures += 1
            journal_append(journal, {"event": "pair_done", "family": family,
                                     "rung": rung, "exit_code": code,
                                     "wall_seconds": secs})
            print(f"{family} @ {rung}: exit={code} {secs}s", flush=True)
    journal_append(journal, {"event": "run_end", "pairs_failed": failures})
    print(f"confirmatory walk complete; {failures} pair(s) exited nonzero",
          flush=True)
    # Exit 0 even with failures: the walk itself succeeded in attempting every
    # pair, and each failure is journaled. A nonzero exit here would say the
    # PASS failed, which is an outcome claim this tool is not allowed to make.
    return 0


if __name__ == "__main__":
    sys.exit(main())
