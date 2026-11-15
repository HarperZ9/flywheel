#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.bench_domains -- the regression corpus for the domain rule packs.

`corpus/domains/expect.json` names, for each sample, the domain profile to check it
under and the exact set of rule-pack categories it must produce. A flagged
sample must produce exactly its listed categories; a clean sample must produce
none of them and pass its profile's gate. A mismatch in either direction counts,
so a pack that stops firing and a pack that starts firing on clean text both
fail the run.

The samples are short and synthetic, written to exercise each rule. They measure
that the rules still do what they did, and nothing about recall or precision on
real documents. The exit code is the number of mismatches.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.normpath(os.path.join(HERE, "..", "..", "corpus", "domains"))


def _pack_categories():
    from . import rules_ext
    return rules_ext.categories()


def run_one(path, profile_name):
    """(pack categories found, gate) for one sample under its profile."""
    from . import checkext, domains
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    r = checkext.check_text(text, profile=domains.load_profile(profile_name))
    cats = {f["category"] for f in r["high"] + r["medium"] + r["low"]}
    return cats & _pack_categories(), r["gate"]


def results(corpus=DEFAULT_CORPUS):
    """One row per sample: (name, profile, expected, found, gate, ok)."""
    with open(os.path.join(corpus, "expect.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    rows = []
    for name, entry in sorted(spec.items()):
        if name.startswith("_"):
            continue
        found, gate = run_one(os.path.join(corpus, name), entry["profile"])
        expected = set(entry["expect"])
        ok = found == expected and (expected or gate == "ok")
        rows.append((name, entry["profile"], expected, found, gate, bool(ok)))
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    corpus = argv[0] if argv else DEFAULT_CORPUS
    if not os.path.isfile(os.path.join(corpus, "expect.json")):
        print(f"[bench-domains] no expect.json under {corpus}")
        return 0
    rows = results(corpus)
    print(f"[bench-domains] corpus: {corpus}")
    for name, profile, expected, found, gate, ok in rows:
        mark = " " if ok else "X"
        extra = "" if ok else f"  expected {sorted(expected)}, found {sorted(found)}"
        print(f"{mark} {name:<34} [{profile}] {len(found)} pack rule(s), gate {gate}{extra}")
    misses = sum(1 for r in rows if not r[5])
    print(f"[bench-domains] samples {len(rows)}, mismatches {misses} "
          f"(synthetic samples: a regression check, not a recall or precision measure)")
    return misses


if __name__ == "__main__":
    sys.exit(main())
