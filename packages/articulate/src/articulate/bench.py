#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate-bench.py

A regression check for the Articulate writing-device rules. It runs the
detector over a small labeled corpus and prints, per file, what it raised,
and fails when a file stops raising, or starts raising, what it should. The
counts are no measure of detection: the corpus holds nine files.

The measure against ground truth is the known-provenance corpus in
corpus/provenance/ (scripts/provenance_eval.py). There the bench call flags
all 84 AI texts and 57 of 75 human texts, so it is a style check. It is not an
authorship test. Older outside detector results (Pangram) can still be
recorded per sample in `<corpus>/pangram-records.jsonl`, keyed by the text's
SHA-256 with the model version and the date observed, for cross-reference;
they are printed but never used as an optimization target. The tool flags; it
never rewrites toward a score.

Corpus layout:
    articulate-corpus/human/<name>.txt   human-authored (expect: clean)
    articulate-corpus/ai/<name>.txt      AI-authored    (expect: flagged)
    articulate-corpus/pangram-records.jsonl  optional: versioned references
    articulate-corpus/<any>/<name>.pangram   older unversioned reference

Usage: python articulate-bench.py [corpus_dir]
Exit code is the number of files that changed what they raise (0 = none), for CI use.
"""
import json
import os
import subprocess
import sys

from .bench_house import HOUSE_BUDGET_MS, house_text  # noqa: E402,F401  (python -m articulate.bench house)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.normpath(os.path.join(HERE, "..", "..", "corpus"))


def run_checker(path):
    from . import detector
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {"high": 0, "medium": 0, "low": 0, "clean": True, "cadence": {}}
    r = detector.check_text(text)
    cad = dict(r["cadence"])
    cad["score"] = r["texture_score"]
    cad["elevated"] = r["elevated"]
    return {"high": len(r["high"]), "medium": len(r["medium"]), "low": len(r["low"]),
            "clean": r["clean"], "cadence": cad}


def pangram_ref(path, corpus=None, records=None):
    """The versioned reference for one file; see pangram_records."""
    from . import pangram_records
    corpus = corpus or os.path.dirname(os.path.dirname(path))
    return pangram_records.reference(corpus, path, records)


def expected_miss(path):
    """A sidecar <name>.expect containing 'miss' marks a known ceiling (e.g.
    device-clean AI a rule detector cannot catch). It stays visible in the
    table but does not count as a regression, so the gate is green until real
    detection breaks."""
    side = os.path.splitext(path)[0] + ".expect"
    if os.path.isfile(side):
        try:
            return "miss" in open(side, encoding="utf-8").read().lower()
        except OSError:
            return False
    return False


def collect(corpus, label):
    d = os.path.join(corpus, label)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in sorted(os.listdir(d))
            if n.lower().endswith((".txt", ".md")) and not n.endswith(".pangram")]


def main(argv):
    if argv and argv[0] == "house":
        from .bench_house import main as house_main
        return house_main(argv[1:])
    corpus = argv[0] if argv else DEFAULT_CORPUS
    ai_files = collect(corpus, "ai")
    human_files = collect(corpus, "human")
    if not ai_files and not human_files:
        print(f"[bench] no corpus at {corpus}/ai or {corpus}/human")
        return 0

    from . import pangram_records
    records = pangram_records.load(corpus)
    misses = 0
    print(f"[bench] corpus: {corpus}")
    print(f"{'label':<7} {'verdict':<9} {'H/M/L':<10} {'texture':<22} file")
    print("-" * 78)

    def is_flagged(r):
        cad = r["cadence"]
        return (r["high"] + r["medium"]) > 0 or bool(cad.get("elevated"))

    def row(path, truth):
        nonlocal misses
        r = run_checker(path)
        flagged = is_flagged(r)
        # A correct call: AI is flagged, human is left clean.
        correct = flagged if truth == "ai" else (not flagged)
        known = expected_miss(path)
        if not correct and not known:
            misses += 1
        cad = r["cadence"]
        tex = f"score {cad.get('score', 0)}"
        if cad.get("uniform"):
            tex += " uniform"
        if cad.get("repetitive_openers"):
            tex += " openers"
        verdict = "FLAGGED" if flagged else "clean"
        mark = " " if correct else ("~" if known else "X")
        hml = f"{r['high']}/{r['medium']}/{r['low']}"
        ref = pangram_ref(path, corpus, records)
        name = os.path.basename(path) + (f"   [pangram: {ref}]" if ref else "")
        print(f"{truth:<7} {verdict:<9} {hml:<10} {tex:<22}{mark} {name}")

    for p in ai_files:
        row(p, "ai")
    for p in human_files:
        row(p, "human")

    n_ai, n_human = len(ai_files), len(human_files)
    ai_flagged = sum(1 for p in ai_files if is_flagged(run_checker(p)))
    human_clean = sum(1 for p in human_files if not is_flagged(run_checker(p)))
    print("-" * 78)
    if n_ai:
        print(f"[bench] ai/ files flagged:     {ai_flagged}/{n_ai}")
    if n_human:
        print(f"[bench] human/ files clean:    {human_clean}/{n_human}")
    print(f"[bench] regressions (unexpected misses): {misses}   "
          f"[~ = known ceiling, not a regression]")
    print("[bench] note: a regression check on a small corpus, not a detection measure. "
          "On known-provenance text the same call flags 57 of 75 human texts; "
          "see corpus/provenance/README.md.")
    return misses + _domain_misses(corpus)


def _domain_misses(corpus):
    """Mismatches in the domain rule-pack corpus under domains/, if present."""
    from . import bench_domains
    domains = os.path.join(corpus, "domains")
    if not os.path.isfile(os.path.join(domains, "expect.json")):
        return 0
    print()
    return bench_domains.main([domains])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
