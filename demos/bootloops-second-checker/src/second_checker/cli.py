"""Command line for the clean-room RECEIPT v1.0 checker.

    python -m second_checker verify --system-jsonl SYS.jsonl --witness W [W ...]
        [--table CLAIMED.json] [--report OUT.json] [-q]

Exit codes follow WITNESS_FORMAT.md: 0 all PASS, 1 any FAIL, 2 malformed
input (including no witnesses found).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

from .checker import FAIL, MALFORMED, PASS, Malformed, parse_row, parse_witness, verify


def load_system_jsonl(path: str) -> list[dict]:
    """One JSON object per non-blank line: {"<col_id>": value}. Raw, unreduced."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise Malformed(f"{path}:{lineno}: bad JSON ({exc})") from exc
            if not isinstance(obj, dict):
                raise Malformed(f"{path}:{lineno}: row is not an object")
            rows.append(obj)
    return rows


def expand_witness_args(args: list[str]) -> list[str]:
    out: list[str] = []
    for a in args:
        if os.path.isdir(a):
            out.extend(sorted(glob.glob(os.path.join(a, "*.json"))))
        elif any(ch in a for ch in "*?["):
            out.extend(sorted(glob.glob(a)))
        else:
            out.append(a)
    return out


class ReducedSystem:
    """Caches the system reduced mod each prime that witnesses ask for."""

    def __init__(self, raw_rows: list[dict]):
        self.raw = raw_rows
        self._cache: dict[int, list[dict[int, int]]] = {}

    def at(self, p: int) -> list[dict[int, int]]:
        if p not in self._cache:
            self._cache[p] = [parse_row(r, p, where=f"system row {i}")
                              for i, r in enumerate(self.raw)]
        return self._cache[p]


def check_files(system: ReducedSystem, paths: list[str], table: dict | None):
    results = []
    for path in paths:
        t0 = time.perf_counter()
        rec = {"witness": os.path.basename(path)}
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
            w = parse_witness(obj)
            claimed = None
            if table is not None:
                claimed = table.get(str(w.target))
                if claimed is None:
                    claimed = table.get(w.target)
            v = verify(system.at(w.p), w, claimed=claimed)
            rec.update(target=w.target, p=w.p, verdict=v.verdict, reason=v.reason)
        except (OSError, json.JSONDecodeError, Malformed) as exc:
            rec.update(verdict=MALFORMED, reason=str(exc))
        rec["seconds"] = round(time.perf_counter() - t0, 6)
        results.append(rec)
    return results


def exit_code(results) -> int:
    if not results or any(r["verdict"] == MALFORMED for r in results):
        return 2
    if any(r["verdict"] == FAIL for r in results):
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="second_checker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--system-jsonl", required=True)
    v.add_argument("--witness", nargs="+", required=True)
    v.add_argument("--table")
    v.add_argument("--report")
    v.add_argument("-q", action="store_true")
    a = ap.parse_args(argv)
    try:
        system = ReducedSystem(load_system_jsonl(a.system_jsonl))
        table = None
        if a.table:
            with open(a.table, encoding="utf-8") as fh:
                table = json.load(fh)
    except (OSError, json.JSONDecodeError, Malformed) as exc:
        print(json.dumps({"rc": 2, "error": str(exc)}))
        return 2
    results = check_files(system, expand_witness_args(a.witness), table)
    rc = exit_code(results)
    report = {"rc": rc, "n": len(results),
              "n_pass": sum(r["verdict"] == PASS for r in results),
              "n_fail": sum(r["verdict"] == FAIL for r in results),
              "n_malformed": sum(r["verdict"] == MALFORMED for r in results),
              "rows": [] if a.q else results}
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump({**report, "rows": results}, fh, indent=1, sort_keys=True)
    print(json.dumps(report, indent=1, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
