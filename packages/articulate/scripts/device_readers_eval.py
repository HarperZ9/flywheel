#!/usr/bin/env python
"""Score the device readers (articulate.devices) against the v2 fixture.

For every split of tests/data/core_devices/devices_v2.json (dev, heldout,
heldout-independent) and every device, report recall and false-positive rate
with Wilson intervals. For antithesis, tricolon and anaphora also report the
two earlier readouts (the line checker and the sentence-run reader), so each
row reads before and after. Then the metamer and isomer pairs of passages.json
under the new readers, and the fairness comparison on the Liang essays and
PERSUADE learners for the readers that the earlier report measured.

The readers report shapes; none of them gates a check. Nothing here changes a
rule or a text to move a number. Counts only. Standard library only.

Usage: python scripts/device_readers_eval.py [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import core_readouts_lib as L  # noqa: E402
import provenance_common as P  # noqa: E402
from articulate import devices  # noqa: E402

V2 = ROOT / "tests" / "data" / "core_devices" / "devices_v2.json"
V1 = ROOT / "tests" / "data" / "core_devices" / "passages.json"
LIANG = pathlib.Path(os.environ.get("ARTICULATE_LIANG_ESSAYS", "liang-essays"))
BEFORE = ("antithesis", "tricolon", "anaphora")


def found(text):
    return {h["device"] for h in devices.analyze(text)["findings"]}


def score(items, names, reader):
    out = {}
    for d in names:
        rows = [{"label": d in it["devices"], "read": {"x": reader(it, d)}} for it in items]
        c = L.confusion(rows, "x")
        c["misses"] = [it["id"] for it in items if d in it["devices"] and not reader(it, d)]
        c["false_alarms"] = [it["id"] for it in items if d not in it["devices"] and reader(it, d)]
        out[d] = c
    return out


def splits(fx):
    by = {}
    for it in fx["items"]:
        it["_after"] = found(it["text"])
        it["_before"] = L.read_all(it["text"])
        by.setdefault(it["split"], []).append(it)
    out = {}
    for name, items in by.items():
        out[name] = {
            "n": len(items),
            "after": score(items, fx["devices"], lambda it, d: d in it["_after"]),
            "before_line": score(items, BEFORE, lambda it, d: it["_before"][f"{d}/line"]),
            "before_runs": score(items, BEFORE, lambda it, d: it["_before"][f"{d}/runs"]),
        }
    return out


def pairs(fx1):
    rows = []
    for p in fx1["metamer_pairs"] + fx1["isomer_pairs"]:
        a, b = p["device"] in found(p["a"]), p["device"] in found(p["b"])
        rows.append({"id": p["id"], "device": p["device"], "device_kept": p["device_kept"],
                     "a": a, "b": b, "flip": a != b})
    kept = [r for r in rows if r["device_kept"]]
    gone = [r for r in rows if not r["device_kept"]]
    return {"rows": rows, "kept": len(kept), "kept_flips": sum(r["flip"] for r in kept),
            "kept_both_miss": sum(1 for r in kept if not r["a"] and not r["b"]),
            "removed": len(gone), "removed_stuck": sum(1 for r in gone if r["b"])}


def _dir(name):
    return [found(f.read_text(encoding="utf-8", errors="replace"))
            for f in sorted((LIANG / name).glob("*.txt"))]


def fairness(names):
    groups = {}
    if LIANG.is_dir():
        groups["toefl"] = _dir("TOEFL_real_91")
        groups["college_win0"] = _dir("CollegeEssay_real_70.win0")
    ell, other = [], []
    for doc in P.load_manifest()["documents"]:
        status = doc.get("group", {}).get("ell_status")
        if doc["class"] != "human" or status not in ("Yes", "No"):
            continue
        text = P.read_checked(doc)
        if text is not None:
            (ell if status == "Yes" else other).append(found(text))
    groups["persuade_ell"], groups["persuade_other"] = ell, other
    out = {}
    for d in names:
        row = {g: f"{sum(d in r for r in rs)}/{len(rs)}" for g, rs in groups.items()}
        for a, b in (("toefl", "college_win0"), ("persuade_ell", "persuade_other")):
            if groups.get(a) and groups.get(b):
                ka, kb = sum(d in r for r in groups[a]), sum(d in r for r in groups[b])
                row[f"{a}_minus_{b}"] = L.newcombe(ka, len(groups[a]), kb, len(groups[b]))
        out[d] = row
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    fx = json.loads(V2.read_text(encoding="utf-8"))
    fx1 = json.loads(V1.read_text(encoding="utf-8"))
    result = {"splits": splits(fx), "pairs": pairs(fx1), "fairness": fairness(fx["devices"])}
    for items in [fx["items"]]:
        for it in items:
            it.pop("_after", None)
            it.pop("_before", None)
    text = json.dumps(result, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
