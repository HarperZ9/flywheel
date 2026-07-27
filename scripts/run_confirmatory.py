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


def journal_append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def run_pair(family: str, rung: str, out: str) -> tuple[int, float]:
    cmd = [sys.executable, str(REPO / "scripts" / "run_demo_pool.py"),
           "--confirmatory", "--family", family, "--rung", rung, "--out", out]
    start = time.time()
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    return proc.returncode, round(time.time() - start, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="artifacts/pool")
    ap.add_argument("--journal", default="artifacts/pool/confirmatory-journal.jsonl")
    args = ap.parse_args()

    journal = REPO / args.journal
    journal_append(journal, {"event": "run_start", "pairs": len(FAMILIES) * len(RUNGS)})
    failures = 0
    for family in FAMILIES:
        for rung in RUNGS:
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
