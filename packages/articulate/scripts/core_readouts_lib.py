"""Readouts and statistics for the CORE device measurements.

A readout maps a text to True when a detector reports a device. Each device has
two readouts where Articulate has two implementations: the line checker
(checkext.check_text, the path `articulate check` uses) and the sentence-run
reader (voice_devices.analyze). The statistics are Wilson intervals for rates,
Newcombe hybrid intervals for differences of rates, and a percentile bootstrap
for pooled rate ratios.

Measurement only. Nothing here rewrites text or tunes a rule toward a score.
Standard library only.
"""
from __future__ import annotations

import math
import random

from articulate import checkext, voice_devices

ANTITHESIS_CATS = frozenset({"antithesis", "corrective-negation", "negative-parallel",
                             "contrast-pair"})


def _findings(result):
    return result["high"] + result["medium"] + result["low"]


def line_check(text):
    """The default `articulate check` result for text."""
    return checkext.check_text(text)


def _antithesis_line(result):
    return any(f["category"] in ANTITHESIS_CATS or "antithesis" in f.get("label", "")
               for f in _findings(result))


def _category(name):
    return lambda result: any(f["category"] == name for f in _findings(result))


def _tell(tell_id):
    return lambda analysis: analysis["counts"].get(tell_id, 0) > 0


# (device, implementation) -> (source, predicate). source "line" reads a
# check_text result; source "runs" reads a voice_devices.analyze result.
READOUTS = {
    ("antithesis", "line"): ("line", _antithesis_line),
    ("antithesis", "runs"): ("runs", _tell("split-antithesis")),
    ("tricolon", "line"): ("line", _category("rule-of-three")),
    ("tricolon", "runs"): ("runs", _tell("tricolon")),
    ("anaphora", "line"): ("line", _category("anaphora")),
    ("anaphora", "runs"): ("runs", _tell("anaphora-run")),
    ("filler-intensifier", "line"): ("line", _category("filler-intensifier")),
}


def read_all(text):
    """Every readout's boolean for one text, plus the checker's word count."""
    line = line_check(text)
    runs = voice_devices.analyze(text)
    src = {"line": line, "runs": runs}
    out = {f"{d}/{impl}": bool(pred(src[s])) for (d, impl), (s, pred) in READOUTS.items()}
    out["_words"] = line["cadence"]["words"]
    out["_counts"] = {
        "filler-intensifier": sum(1 for f in _findings(line)
                                  if f["category"] == "filler-intensifier"),
    }
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None, None)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(p, 3), round(max(0.0, mid - half), 3), round(min(1.0, mid + half), 3))


def newcombe(k1, n1, k2, n2):
    """Difference p1 - p2 with the Newcombe hybrid score interval (method 10)."""
    p1, l1, u1 = wilson(k1, n1)
    p2, l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (round(d, 3), round(lo, 3), round(hi, 3))


def rate_ratio_boot(a, b, B=4000, seed=20261026):
    """Pooled per-1,000-word ratio of group a to group b, resampling documents.
    a and b are lists of (count, words). Returns (ratio, lo, hi) or None."""
    def pooled(xs):
        w = sum(x[1] for x in xs)
        return sum(x[0] for x in xs) / w * 1000 if w else 0.0
    ra, rb = pooled(a), pooled(b)
    if rb == 0:
        return (math.inf if ra else None, None, None)
    rng = random.Random(seed)
    stats = []
    for _ in range(B):
        sa = [rng.choice(a) for _ in a]
        sb = [rng.choice(b) for _ in b]
        pb = pooled(sb)
        stats.append(pooled(sa) / pb if pb else math.inf)
    stats.sort()
    return (round(ra / rb, 2), round(stats[int(0.025 * B)], 2), round(stats[int(0.975 * B) - 1], 2))


def confusion(items, key):
    """Recall and false-positive rate of readout `key` against item labels.
    items: dicts with 'label' (bool) and 'read' (dict of readouts)."""
    tp = sum(1 for it in items if it["label"] and it["read"][key])
    pos = sum(1 for it in items if it["label"])
    fp = sum(1 for it in items if not it["label"] and it["read"][key])
    neg = sum(1 for it in items if not it["label"])
    return {"tp": tp, "pos": pos, "recall": wilson(tp, pos),
            "fp": fp, "neg": neg, "fpr": wilson(fp, neg)}
