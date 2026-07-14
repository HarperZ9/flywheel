"""Audit the hard lane's oracles with non-solutions (UTBoost-style).

Every uplift number stands on the oracles' ability to refuse wrong code.
This audit runs a battery of non-solutions against every task's hidden
tests:

  empty    an empty candidate module
  stub     every top-level def returns None (the admission-gate stub)
  const0 / conststr / constlist   the stub returning 0 / "" / []
  mutant   the reference with its first binary operator flipped

A battery member that PASSES is a false-pass. empty/stub/const passes
are hard flags (the oracle accepted nothing-code); a mutant pass is a
review flag (rarely the mutation is semantically neutral). The reference
must still pass or the task is flagged broken-reference. Usage:

  python scripts/oracle_strength_audit.py [--tasks-file tasks/curated/hard_v2.jsonl]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.task_curator import _run_with, _stub_solution  # noqa: E402
from run_uplift_live import load_specs                      # noqa: E402

_MUTATIONS = ((" + ", " - "), (" - ", " + "), (" < ", " <= "),
              (" > ", " >= "), (" == ", " != "), (" * ", " + "))


def _mutant(solution: str) -> "str | None":
    for old, new in _MUTATIONS:
        if old in solution:
            m = solution.replace(old, new, 1)
            if m != solution:
                return m
    return None


def _battery(solution: str) -> dict:
    probes = {"empty": ""}
    stub = _stub_solution(solution)
    if stub:
        probes["stub"] = stub
        probes["const0"] = stub.replace("return None", "return 0")
        probes["conststr"] = stub.replace("return None", "return ''")
        probes["constlist"] = stub.replace("return None", "return []")
    mut = _mutant(solution)
    if mut:
        probes["mutant"] = mut
    return probes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-file", default="tasks/curated/hard_v2.jsonl")
    ap.add_argument("--out", default="artifacts/audit")
    a = ap.parse_args()
    specs = load_specs(a.tasks_file)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = Path(a.out) / f"work_{stamp}"
    rows, hard_flags, review_flags, broken = [], 0, 0, 0
    t0 = time.time()
    for spec in specs:
        row = {"task_id": spec.task_id, "false_passes": [],
               "reference_ok": True}
        if not _run_with(spec, work, spec.solution, "ref"):
            row["reference_ok"] = False
            broken += 1
        else:
            for name, text in _battery(spec.solution).items():
                if _run_with(spec, work, text, name):
                    row["false_passes"].append(name)
            hard = [f for f in row["false_passes"] if f != "mutant"]
            if hard:
                hard_flags += 1
            elif "mutant" in row["false_passes"]:
                review_flags += 1
        rows.append(row)
        shutil.rmtree(work, ignore_errors=True)
        print(f"{spec.task_id}: "
              f"{'BROKEN-REF' if not row['reference_ok'] else ''}"
              f"{','.join(row['false_passes']) or 'clean'}", flush=True)
    doc = {"schema": "flywheel.oracle-strength/v1",
           "tasks_file": a.tasks_file, "n_tasks": len(rows),
           "hard_flags": hard_flags, "review_flags": review_flags,
           "broken_reference": broken,
           "clean": sum(1 for r in rows
                        if r["reference_ok"] and not r["false_passes"]),
           "rows": rows, "wall_seconds": round(time.time() - t0, 1),
           "note": "a false-pass names a probe the oracle accepted; "
                   "empty/stub/const are hard flags, mutant passes need "
                   "review (a mutation can be semantically neutral)"}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"oracle_strength_{stamp}.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nhard flags: {hard_flags}, review: {review_flags}, "
          f"broken refs: {broken}, clean: {doc['clean']}/{len(rows)}")
    print(f"artifact: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
