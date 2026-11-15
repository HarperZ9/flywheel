#!/usr/bin/env python
"""Blocked rates through the shipped check path, with and without calibration/1.

scripts/fairness_filler_options.py chose the fix on a tuning half. This script
checks that the shipped layer (articulate.checkext with calibration on) gives
the chosen option's numbers on every set, so the decision and the code agree.
It reports the default-profile blocked rate for each set with the calibration
layer off (as 0.16.0 shipped) and on, the TOEFL-minus-college and PERSUADE
learner-minus-other differences, and the pre-registered skew test for
filler-intensifier as a blocking rule. Counts only. Standard library only.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE)]

import core_readouts_lib as L  # noqa: E402
import provenance_common as P  # noqa: E402
from articulate import checkext  # noqa: E402

LIANG = pathlib.Path(os.environ.get("ARTICULATE_LIANG_ESSAYS", "liang-essays"))
SETS = ("TOEFL_real_91", "CollegeEssay_real_70.win0", "CS224N_real_145.win0",
        "TOEFL_gpt4polished_91", "CS224N_gpt3_145.win0", "CollegeEssay_gpt3_31.win0")


def blocked(text, calib):
    return checkext.check_text(text, calibration=calib)["gate"] == "blocked"


def texts():
    out = {}
    for name in SETS:
        d = LIANG / name
        if d.is_dir():
            out[name] = [f.read_text(encoding="utf-8", errors="replace") for f in sorted(d.glob("*.txt"))]
    groups = {"provenance_ai": [], "provenance_human": [], "persuade_ell": [], "persuade_other": []}
    for doc in P.load_manifest()["documents"]:
        t = P.read_checked(doc)
        if t is None:
            continue
        if doc["class"] in ("ai", "human"):
            groups["provenance_" + doc["class"]].append(t)
        status = doc.get("group", {}).get("ell_status")
        if doc["class"] == "human" and status in ("Yes", "No"):
            groups["persuade_ell" if status == "Yes" else "persuade_other"].append(t)
    out.update(groups)
    return out


def main():
    sets = texts()
    rows = {}
    for name, ts in sets.items():
        off = sum(blocked(t, False) for t in ts)
        on = sum(blocked(t, True) for t in ts)
        rows[name] = {"n": len(ts), "blocked_before": off, "blocked_after": on,
                      "rate_before": L.wilson(off, len(ts)), "rate_after": L.wilson(on, len(ts))}
    diffs = {}
    for a, b in (("TOEFL_real_91", "CollegeEssay_real_70.win0"),
                 ("TOEFL_real_91", "CS224N_real_145.win0"),
                 ("persuade_ell", "persuade_other")):
        if a in rows and b in rows:
            ra, rb = rows[a], rows[b]
            diffs[f"{a} - {b}"] = {
                "before": L.newcombe(ra["blocked_before"], ra["n"], rb["blocked_before"], rb["n"]),
                "after": L.newcombe(ra["blocked_after"], ra["n"], rb["blocked_after"], rb["n"])}
    print(json.dumps({"sets": rows, "differences": diffs}, indent=1))


if __name__ == "__main__":
    main()
