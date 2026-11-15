"""Uniform adapters over the three checkers: sc-py, sc-js and core.py (BootLoops).

Every adapter takes (system_jsonl, [witness paths], table or None) and returns
{basename: (verdict, reason, seconds)} with verdict in PASS / FAIL / MALFORMED.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

from second_checker.checker import MALFORMED, Malformed, parse_witness, verify  # noqa: E402
from second_checker.cli import ReducedSystem, load_system_jsonl  # noqa: E402


def sc_py(system_path, paths, table=None):
    out = {}
    try:
        system = ReducedSystem(load_system_jsonl(system_path))
    except Malformed as exc:
        return {os.path.basename(q): (MALFORMED, str(exc), 0.0) for q in paths}
    for q in paths:
        t0 = time.perf_counter()
        try:
            with open(q, encoding="utf-8") as fh:
                w = parse_witness(json.load(fh))
            claimed = None if table is None else table.get(str(w.target))
            v = verify(system.at(w.p), w, claimed=claimed)
            res = (v.verdict, v.reason)
        except (Malformed, json.JSONDecodeError, OSError) as exc:
            res = (MALFORMED, str(exc))
        out[os.path.basename(q)] = (*res, time.perf_counter() - t0)
    return out


def sc_js(system_path, paths, table=None):
    """JS checker has no table mode; returns None when a table is requested."""
    if table is not None:
        return None
    out = {}
    chunk = 200  # keep Windows command lines short
    for k in range(0, len(paths), chunk):
        part = paths[k:k + chunk]
        t0 = time.perf_counter()
        r = subprocess.run(["node", os.path.join(REPO, "js", "check.mjs"), system_path, *part],
                           capture_output=True, text=True)
        dt = (time.perf_counter() - t0) / max(len(part), 1)
        for line in r.stdout.splitlines():
            rec = json.loads(line)
            out[rec["witness"]] = (rec["verdict"], rec["reason"], dt)
        if r.returncode not in (0, 1, 2):
            raise RuntimeError(f"js checker crashed: {r.stderr[-500:]}")
    return out


_CORE = None


def _core(bl_root):
    global _CORE
    if _CORE is None:
        sys.path.insert(0, os.path.join(bl_root, "tools", "trust", "receipt"))
        import core  # BootLoops core.py, pinned commit
        _CORE = core
    return _CORE


def core_py(bl_root, system_path, paths, table=None):
    core = _core(bl_root)
    out = {}
    try:
        rows = core.load_system_jsonl(system_path)
    except core.MalformedInput as exc:
        return {os.path.basename(q): (MALFORMED, str(exc), 0.0) for q in paths}
    for q in paths:
        t0 = time.perf_counter()
        try:
            wit = core.load_witness(q)
            trow = None
            if table is not None:
                raw = table.get(str(wit["target_col"]))
                trow = None if raw is None else {int(k): int(v) for k, v in raw.items()}
            ok, det = core.verify_row(rows, wit, table_row=trow)
            res = ("PASS" if ok else "FAIL", det.get("reason", ""))
        except core.MalformedInput as exc:
            res = (MALFORMED, str(exc))
        except Exception as exc:  # a crash is recorded, never hidden
            res = ("CRASH", f"{type(exc).__name__}: {exc}")
        out[os.path.basename(q)] = (*res, time.perf_counter() - t0)
    return out
