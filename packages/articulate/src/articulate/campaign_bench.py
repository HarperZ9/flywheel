"""Bench for the campaign signals: precision, recall, per-stratum false positives,
the fairness bound, cluster pair metrics, and controls that must fail.

    python -m articulate.campaign_bench [--split dev|heldout|all] [--json]

Targets were set after a baseline on the dev split (docs/campaign.md records
both). The heldout split was scored once after the dev changes were frozen.
A control is a deliberately bad detector or a scrambled label set; the bench
asserts that each control FAILS the targets, so a passing bench cannot come
from targets loose enough to accept anything.
"""
import argparse
import json
import math
import random
import re
from itertools import combinations

from . import campaign_cluster, campaign_corpus, campaign_persona, campaign_promo

TARGETS = {"precision": 0.90, "recall": 0.80, "fpr": 0.05, "pair_precision": 0.95,
           "pair_recall": 0.90}
FAIRNESS_MARGIN = 0.10  # no stratum's FPR may exceed the overall FPR by more than this


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 3), round((c + h) / d, 3)]


def predict(row):
    if row["kind"] == "bio":
        return campaign_persona.assess(row["text"], row["platform"])["template"]
    return campaign_promo.assess(row["text"])["template"]


def confusion(rows, preds):
    tp = sum(1 for r, p in zip(rows, preds) if p and r["label"])
    fp = sum(1 for r, p in zip(rows, preds) if p and not r["label"])
    fn = sum(1 for r, p in zip(rows, preds) if not p and r["label"])
    neg = sum(1 for r in rows if not r["label"])
    pos = sum(1 for r in rows if r["label"])
    return {"tp": tp, "fp": fp, "fn": fn, "positives": pos, "negatives": neg,
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "recall": round(tp / pos, 3) if pos else 0.0,
            "fpr": round(fp / neg, 3) if neg else 0.0,
            "recall_ci": wilson(tp, pos), "fpr_ci": wilson(fp, neg)}


def strata(rows, preds, key):
    out = {}
    for name in sorted({r[key] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r[key] == name]
        out[name] = confusion([rows[i] for i in idx], [preds[i] for i in idx])
    return out


def fairness(by_stratum, overall_fpr, margin=FAIRNESS_MARGIN):
    rows, ok = {}, True
    for name, m in by_stratum.items():
        if not m["negatives"]:
            continue
        within = m["fpr"] <= overall_fpr + margin
        ok = ok and within
        rows[name] = {"fpr": m["fpr"], "negatives": m["negatives"], "fpr_ci": m["fpr_ci"],
                      "within_bound": within}
    return {"margin": margin, "overall_fpr": overall_fpr, "passed": ok, "strata": rows,
            "note": "small strata: an upper interval above the bound is not ruled out"}


def meets(m):
    return (m["precision"] >= TARGETS["precision"] and m["recall"] >= TARGETS["recall"]
            and m["fpr"] <= TARGETS["fpr"])


def score_kind(rows, preds):
    m = confusion(rows, preds)
    by = strata(rows, preds, "stratum")
    return {"overall": m, "meets_targets": meets(m), "by_stratum": by,
            "by_platform": strata(rows, preds, "platform"),
            "fairness": fairness(by, m["fpr"])}


def cluster_pairs(threshold=0.5, texts_fn=None):
    b = campaign_corpus.batch()
    texts = [texts_fn(x["text"]) if texts_fn else x["text"] for x in b]
    clusters = campaign_cluster.cluster(texts, threshold=threshold)
    pred = {p for c in clusters for p in combinations(c["members"], 2)}
    gold = {(i, j) for i, j in combinations(range(len(b)), 2)
            if b[i]["campaign"] and b[i]["campaign"] == b[j]["campaign"]}
    tp = len(pred & gold)
    return {"pairs_predicted": len(pred), "pairs_gold": len(gold), "tp": tp,
            "pair_precision": round(tp / len(pred), 3) if pred else 0.0,
            "pair_recall": round(tp / len(gold), 3) if gold else 0.0, "threshold": threshold}


def cluster_meets(m):
    return (m["pair_precision"] >= TARGETS["pair_precision"]
            and m["pair_recall"] >= TARGETS["pair_recall"])


def controls(rows):
    """Each control must fail the targets. Returns {name: failed_as_required}."""
    out = {}
    posts = [r for r in rows if r["kind"] == "post"]
    bios = [r for r in rows if r["kind"] == "bio"]
    out["always_flag_posts"] = not meets(confusion(posts, [True] * len(posts)))
    out["always_flag_bios"] = not meets(confusion(bios, [True] * len(bios)))
    real = [predict(r) for r in bios]
    shuffled = [dict(r, label=lab) for r, lab in
                zip(bios, random.Random(7).sample([r["label"] for r in bios], len(bios)))]
    out["shuffled_labels_bios"] = not meets(confusion(shuffled, real))
    kw = re.compile(r"\$[A-Z]{2,6}|\b(crypto|bitcoin|btc|eth|web3|blockchain)\b", re.I)
    out["keyword_bios"] = not meets(confusion(bios, [bool(kw.search(r["text"])) for r in bios]))
    spec = campaign_promo.SPEC
    out["spec_number_posts"] = not meets(confusion(posts, [bool(spec.search(r["text"]))
                                                           for r in posts]))
    out["exact_match_clusters"] = not cluster_meets(cluster_pairs(threshold=0.999))
    out["topic_word_clusters"] = not cluster_meets(_topic_pairs())
    return out


def _topic_pairs():
    """A bad clusterer: join any two posts that name the product. Organic replies do too."""
    b = campaign_corpus.batch()
    hit = [i for i, x in enumerate(b) if re.search(r"ember|northlake", x["text"], re.I)]
    pred = set(combinations(hit, 2))
    gold = {(i, j) for i, j in combinations(range(len(b)), 2)
            if b[i]["campaign"] and b[i]["campaign"] == b[j]["campaign"]}
    tp = len(pred & gold)
    return {"pair_precision": tp / len(pred) if pred else 0.0,
            "pair_recall": tp / len(gold) if gold else 0.0}


def run(split="dev"):
    rows = campaign_corpus.items(None if split == "all" else split)
    preds = [predict(r) for r in rows]
    report = {"split": split, "targets": TARGETS, "fairness_margin": FAIRNESS_MARGIN}
    for kind in ("post", "bio"):
        idx = [i for i, r in enumerate(rows) if r["kind"] == kind]
        report[kind] = score_kind([rows[i] for i in idx], [preds[i] for i in idx])
    report["clusters"] = cluster_pairs()
    report["clusters"]["meets_targets"] = cluster_meets(report["clusters"])
    report["controls"] = controls(rows)
    report["passed"] = (report["post"]["meets_targets"] and report["bio"]["meets_targets"]
                        and report["post"]["fairness"]["passed"]
                        and report["bio"]["fairness"]["passed"]
                        and report["clusters"]["meets_targets"]
                        and all(report["controls"].values()))
    return report


def _line(name, m):
    return (f"{name:12} P {m['precision']:.3f}  R {m['recall']:.3f} {m['recall_ci']}  "
            f"FPR {m['fpr']:.3f} {m['fpr_ci']}  (pos {m['positives']}, neg {m['negatives']})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="articulate.campaign_bench")
    ap.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = run(a.split)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["passed"] else 1
    for kind in ("post", "bio"):
        print(_line(kind, r[kind]["overall"]))
        for name, s in r[kind]["fairness"]["strata"].items():
            print(f"    {name:14} FPR {s['fpr']:.3f} {s['fpr_ci']} n={s['negatives']}"
                  f" {'ok' if s['within_bound'] else 'OVER BOUND'}")
    c = r["clusters"]
    print(f"clusters     pair P {c['pair_precision']:.3f}  pair R {c['pair_recall']:.3f}")
    print("controls     " + ", ".join(f"{k}={'failed' if v else 'PASSED'}"
                                      for k, v in r["controls"].items()))
    print("bench " + ("passed" if r["passed"] else "FAILED"))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
