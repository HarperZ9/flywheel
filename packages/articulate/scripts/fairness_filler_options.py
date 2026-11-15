#!/usr/bin/env python
"""Compare fixes for the filler-intensifier learner skew, with a held-out split.

The September audit found HIGH `filler-intensifier` (really / actually / truly /
genuinely) fires on 26 of 91 TOEFL texts against 2 of 70 length-matched US
college essay windows, and because HIGH blocks under the default profile it
blocks learner writing more often. This script reads the pinned detector once
per document and then applies each candidate fix as a re-tiering of the
detector's own findings, so no rule or text changes:

  baseline   as shipped: the finding is HIGH and blocks under `flavored`
  demote     every filler finding moves to LOW: reported, never blocks
  split      "really" and "actually" move to LOW; "truly" and "genuinely" stay
             HIGH (the GPT-4 rewrites in the audit used truly and genuinely,
             the learners used really)
  density    the finding blocks only when filler words reach 10 or more per
             1,000 words in the document (a register-density condition)

Choice rule, fixed before the held-out numbers are read: on the tuning half
(even-indexed Liang documents) pick the option with the smallest TOEFL minus
college blocked-rate difference whose blocked rate on AI documents of the
known-provenance corpus drops by no more than 2 points against baseline; ties
go to the option that keeps more filler findings blocking. The held-out half
(odd-indexed), PERSUADE learners against other students and the TOEFL GPT-4
rewrites are reported after the choice and never used to make it.

Counts only. No licensed text leaves the machine. Standard library only.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE)]

import core_readouts_lib as L  # noqa: E402
import provenance_common as P  # noqa: E402
from articulate import detector  # noqa: E402

LIANG = pathlib.Path(os.environ.get("ARTICULATE_LIANG_ESSAYS", "liang-essays"))
FILLER = re.compile(r"\b(really|actually|truly|genuinely)\b", re.I)
OPTIONS = ("baseline", "demote", "split", "density")
DENSITY_PER_1K = 10.0


def read(text):
    r = detector.check_text(text)
    words = r["cadence"]["words"] or 1
    hits = [m.group(1).lower() for m in FILLER.finditer(text)]
    other_high = sum(1 for f in r["high"] if f["category"] != "filler-intensifier")
    fillers = [f for f in r["high"] if f["category"] == "filler-intensifier"]
    return {"other_high": other_high, "fillers": fillers, "hits": hits, "words": words}


def blocked(rd, option):
    """Would the default (`flavored`) gate block under this option?"""
    if rd["other_high"]:
        return True
    if not rd["fillers"]:
        return False
    if option == "baseline":
        return True
    if option == "demote":
        return False
    if option == "split":
        return any(f["match"].lower() in ("truly", "genuinely") for f in rd["fillers"])
    if option == "density":
        return len(rd["hits"]) / rd["words"] * 1000 >= DENSITY_PER_1K
    raise ValueError(option)


def rate(reads, option):
    k = sum(blocked(r, option) for r in reads)
    return {"k": k, "n": len(reads), "rate": L.wilson(k, len(reads))}


def dir_reads(name, parity=None):
    files = sorted((LIANG / name).glob("*.txt"))
    if parity is not None:
        files = [f for i, f in enumerate(files) if i % 2 == parity]
    return [read(f.read_text(encoding="utf-8", errors="replace")) for f in files]


def compare(a, b, option):
    ra, rb = rate(a, option), rate(b, option)
    return {"a": f"{ra['k']}/{ra['n']}", "b": f"{rb['k']}/{rb['n']}",
            "diff": L.newcombe(ra["k"], ra["n"], rb["k"], rb["n"])}


def provenance_reads():
    out = {"ai": [], "human": [], "ell": [], "other": []}
    for doc in P.load_manifest()["documents"]:
        text = P.read_checked(doc)
        if text is None:
            continue
        rd = read(text)
        if doc["class"] in ("ai", "human"):
            out[doc["class"]].append(rd)
        ell = doc.get("group", {}).get("ell_status")
        if doc["class"] == "human" and ell in ("Yes", "No"):
            out["ell" if ell == "Yes" else "other"].append(rd)
    return out


def choose(tune, prov):
    base_ai = rate(prov["ai"], "baseline")["rate"][0]
    rows = []
    for opt in OPTIONS:
        d = compare(tune["toefl"], tune["college"], opt)["diff"][0]
        ai = rate(prov["ai"], opt)["rate"][0]
        keeps = sum(blocked(r, opt) for r in prov["ai"] + tune["toefl"] + tune["college"])
        rows.append((opt, d, ai, keeps))
    ok = [r for r in rows if base_ai - r[2] <= 0.02]
    ok.sort(key=lambda r: (round(r[1], 3), -r[3]))
    return ok[0][0], rows


def main():
    tune = {"toefl": dir_reads("TOEFL_real_91", 0),
            "college": dir_reads("CollegeEssay_real_70.win0", 0)}
    held = {"toefl": dir_reads("TOEFL_real_91", 1),
            "college": dir_reads("CollegeEssay_real_70.win0", 1),
            "cs224n": dir_reads("CS224N_real_145.win0", 1)}
    rewrites = dir_reads("TOEFL_gpt4polished_91")
    gpt_abs = dir_reads("CS224N_gpt3_145.win0")
    prov = provenance_reads()
    choice, rows = choose(tune, prov)
    report = {"choice": choice,
              "choice_rows_tuning": [dict(zip(("option", "toefl_minus_college", "ai_blocked",
                                                "blocked_total"), r)) for r in rows],
              "options": {}}
    for opt in OPTIONS:
        report["options"][opt] = {
            "tuning_toefl_vs_college": compare(tune["toefl"], tune["college"], opt),
            "heldout_toefl_vs_college": compare(held["toefl"], held["college"], opt),
            "heldout_toefl_vs_cs224n": compare(held["toefl"], held["cs224n"], opt),
            "persuade_ell_vs_other": compare(prov["ell"], prov["other"], opt),
            "toefl_gpt4_rewrites_blocked": rate(rewrites, opt)["k"],
            "chatgpt_abstracts_blocked": rate(gpt_abs, opt)["k"],
            "provenance_ai_blocked": rate(prov["ai"], opt),
            "provenance_human_blocked": rate(prov["human"], opt),
        }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
