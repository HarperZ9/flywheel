"""Measure Articulate's bench call against known provenance, and compare detectors.

    python scripts/provenance_eval.py [--local-root DIR] [--out corpus/provenance/results.json]

Primary report: precision, recall and false-positive rate of Articulate's
bench call (any high or medium finding, or elevated cadence, under the
default profile) against the ground-truth class, with Wilson 95% intervals,
overall, by genre, by generating model and by English-learner status.
Secondary report: AUROC of Binoculars and Fast-DetectGPT against ground
truth, and how often Binoculars and Articulate agree.

These are measurements. No rule, gate, threshold or editor setting is chosen
from them, and nothing here tunes Articulate. Mixed documents are reported
on their own and count toward neither class.
"""
import argparse
import collections
import json
import sys

import provenance_common as C

sys.path.insert(0, str(C.ROOT / "src"))
from articulate import detector  # noqa: E402

sys.path.insert(0, str(C.ROOT / "scripts"))
from pangram_agreement import auroc, auroc_interval, wilson  # noqa: E402


def articulate_call(text):
    r = detector.check_text(text)
    return bool(r["high"] or r["medium"] or r["cadence"].get("elevated"))


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": wilson(k, n)}


def confusion(rows):
    tp = sum(1 for r in rows if r["flag"] and r["class"] == "ai")
    fp = sum(1 for r in rows if r["flag"] and r["class"] == "human")
    pos = sum(1 for r in rows if r["class"] == "ai")
    neg = sum(1 for r in rows if r["class"] == "human")
    return {"precision": rate(tp, tp + fp), "recall": rate(tp, pos), "fpr": rate(fp, neg)}


def detector_scores(local_root):
    out = collections.defaultdict(dict)
    for line in (C.PROV / "detector-records.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        out[rec["detector"]][rec["text_id"]] = rec
    return out


def rows_for(local_root):
    scores = detector_scores(local_root)
    rows = []
    for doc in C.load_manifest()["documents"]:
        text = C.read_checked(doc, local_root)
        if text is None:
            continue
        row = {"id": doc["id"], "class": doc["class"], "genre": doc["genre"],
               "model": doc.get("generation", {}).get("model"),
               "ell": doc.get("group", {}).get("ell_status"), "flag": articulate_call(text)}
        for name, recs in scores.items():
            rec = recs.get(doc["id"])
            if rec and rec["text_sha256"] == doc["sha256"]:
                # orient every score so that higher reads as more machine-like
                row[name] = -rec["score"] if rec["detector"] == "binoculars" else rec["score"]
        rows.append(row)
    return rows


def detector_auroc(rows, name):
    pos = [r[name] for r in rows if r["class"] == "ai" and name in r]
    neg = [r[name] for r in rows if r["class"] == "human" and name in r]
    a = auroc(pos, neg)
    return {"auroc": round(a, 3) if a is not None else None, "ci95": auroc_interval(pos, neg),
            "n_ai": len(pos), "n_human": len(neg)}


def binoculars_agreement(rows, fpr=0.05):
    """Binoculars called where `fpr` of the human texts here flag. The point is set on this
    corpus, so it flatters Binoculars; it is a reference, not a Binoculars result."""
    human = sorted((r["binoculars"] for r in rows if r["class"] == "human"), reverse=True)
    cut = human[max(0, int(len(human) * fpr) - 1)]
    both = [r for r in rows if r["class"] in ("ai", "human")]
    for r in both:
        r["bino_flag"] = r["binoculars"] > cut
    agree = sum(1 for r in both if r["flag"] == r["bino_flag"])
    return {"threshold_note": f"Binoculars flags above the in-sample {fpr:.0%} human false-positive point",
            "agreement": rate(agree, len(both)),
            "articulate_only": sorted(r["id"] for r in both if r["flag"] and not r["bino_flag"]),
            "binoculars_only": sorted(r["id"] for r in both if r["bino_flag"] and not r["flag"]),
            "binoculars_at_threshold": confusion([dict(r, flag=r["bino_flag"]) for r in both])}


def grouped(rows, key, values=None):
    out = {}
    for v in sorted({r[key] for r in rows if r[key]} if values is None else values):
        sub = [r for r in rows if r[key] == v or (r["class"] == "human" and key == "model")]
        out[v] = confusion(sub)
    return out


def report(rows):
    core = [r for r in rows if r["class"] in ("ai", "human")]
    mixed = [r for r in rows if r["class"] == "mixed"]
    essays = [r for r in core if r["genre"] == "student-essay"]
    return {
        "counts": collections.Counter(f"{r['class']}/{r['genre']}" for r in rows),
        "articulate": {"overall": confusion(core), "by_genre": grouped(core, "genre"),
                       "by_model": grouped(core, "model"),
                       "student_essay_fpr_by_ell": {e: confusion([r for r in essays if r["ell"] in (e, None)])["fpr"]
                                                    for e in ("Yes", "No")},
                       "mixed_flag_rate": rate(sum(r["flag"] for r in mixed), len(mixed))},
        "detectors": {name: {"overall": detector_auroc(core, name),
                             "by_genre": {g: detector_auroc([r for r in core if r["genre"] == g], name)
                                          for g in sorted({r["genre"] for r in core})},
                             "by_model": {m: detector_auroc([r for r in core if r["model"] in (m, None)], name)
                                          for m in sorted({r["model"] for r in core if r["model"]})}}
                      for name in ("binoculars", "fast-detectgpt")},
        "binoculars_vs_articulate": {f"{f:.0%} in-sample human FPR": binoculars_agreement(core, f)
                                     for f in (0.05, 0.10, 0.20)},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--local-root", type=C.pathlib.Path, default=C.DEFAULT_LOCAL)
    ap.add_argument("--out", type=C.pathlib.Path, default=C.PROV / "results.json")
    a = ap.parse_args(argv)
    rows = rows_for(a.local_root)
    res = report(rows)
    res["documents_measured"] = len(rows)
    res["scope"] = ("Measured on this corpus only. A flag names a prose pattern in a text. "
                    "Use other evidence to decide who wrote a text.")
    a.out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(res["articulate"]["overall"], indent=1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
