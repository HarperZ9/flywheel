"""Report how Articulate's bench calls line up with each Pangram model version.

This is a report. It sets no target: no rule, gate, threshold or editor
setting is chosen from it, and the two tools measure different things.
Articulate names prose patterns; Pangram estimates AI involvement. Agreement
says how often the two point the same way on this corpus. It proves nothing
about who wrote any text.

    python scripts/pangram_agreement.py [--json]

For each model version in corpus/pangram-records.jsonl it joins the latest
record per text with the bench call (flagged or clean) and reports, with 95%
intervals: agreement, precision and recall of "flagged" against "Pangram
positive" (any result other than Human), and AUROC of the texture score
against the same reference. Calibration does not apply: Articulate emits no
probability. Every disagreement is listed in both directions.
"""
import json
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
sys.path.insert(0, str(ROOT / "src"))

from articulate import bench, pangram_records as PR  # noqa: E402


def wilson(k, n, z=1.96):
    """Wilson 95% interval for k of n, or None when n is 0."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 3), round(min(1.0, c + h), 3))


def auroc(pos, neg):
    """Mann-Whitney AUROC, ties counted half, or None without both classes."""
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def auroc_interval(pos, neg, reps=2000, seed=0):
    """Percentile bootstrap 95% interval, resampling each class."""
    if len(pos) < 2 or len(neg) < 2:
        return None
    rng = random.Random(seed)
    vals = sorted(auroc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg])
                  for _ in range(reps))
    return (round(vals[int(0.025 * reps)], 3), round(vals[int(0.975 * reps) - 1], 3))


def positive(rec):
    return (rec.get("prediction_short") or result_word(rec)) not in ("Human", "")


def result_word(rec):
    return (rec.get("reported") or "").split(" ")[0]


def joined(corpus=CORPUS):
    """{model: [(text, flagged, texture, pangram_positive)]}, latest record per text."""
    latest = {}
    for rec in PR.load(str(corpus)):
        latest[(rec["model"], rec["text"])] = rec
    out = {}
    for (model, rel), rec in sorted(latest.items()):
        path = corpus / rel
        if not path.is_file() or PR.text_sha256(path) != rec["text_sha256"]:
            continue  # the text changed since it was scored; the record no longer applies
        r = bench.run_checker(str(path))
        flagged = (r["high"] + r["medium"]) > 0 or bool(r["cadence"].get("elevated"))
        out.setdefault(model, []).append((rel, flagged, r["cadence"].get("score", 0), positive(rec)))
    return out


def summarize(rows):
    tp = sum(1 for _, f, _, p in rows if f and p)
    fp = sum(1 for _, f, _, p in rows if f and not p)
    fn = sum(1 for _, f, _, p in rows if not f and p)
    agree = sum(1 for _, f, _, p in rows if f == p)
    pos = [s for _, _, s, p in rows if p]
    neg = [s for _, _, s, p in rows if not p]
    return {"n": len(rows), "pangram_positive": len(pos),
            "agreement": [agree, len(rows), wilson(agree, len(rows))],
            "precision": [tp, tp + fp, wilson(tp, tp + fp)],
            "recall": [tp, tp + fn, wilson(tp, tp + fn)],
            "auroc_texture": [auroc(pos, neg), auroc_interval(pos, neg)],
            "calibration": "not applicable: Articulate emits no probability",
            "flagged_pangram_human": [t for t, f, _, p in rows if f and not p],
            "clean_pangram_positive": [t for t, f, _, p in rows if not f and p]}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    report = {m: summarize(rows) for m, rows in joined().items()}
    if "--json" in argv:
        print(json.dumps(report, indent=1))
        return 0
    for model, s in report.items():
        print(f"model {model}: n {s['n']}, Pangram positive {s['pangram_positive']}")
        for key in ("agreement", "precision", "recall"):
            k, n, ci = s[key]
            print(f"  {key:<10} {k}/{n}  95% {ci}")
        print(f"  auroc      {s['auroc_texture'][0]}  95% {s['auroc_texture'][1]}")
        print(f"  flagged, Pangram Human:   {s['flagged_pangram_human']}")
        print(f"  clean, Pangram positive:  {s['clean_pangram_positive']}")
    print("Agreement is a report, not a target. It says nothing about who wrote a text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
