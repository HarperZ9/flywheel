"""Forecast scoring (upgrade 2026-11-02): Brier and log score per verdict, coverage and ratio error per
quantity. F674 and F675 forecasts missed by factors of 4 to 13 and nobody scored them except by hand.

Spec field, frozen by the lock (ext_sha256):
  "forecasts": {
    "verdicts":   {"V1": 0.30, ...},      probability that the verdict comes out PASS
    "quantities": {"analysis.real_hp.mean_d": {"point": -0.05, "lo": -0.30, "hi": 0.20}, ...}
  }
Scores:
  Brier       (p - o)^2, o = 1 for PASS and 0 for FAIL. Lower is better; 0.25 is the score of p = 0.5.
  log score   ln(p) for PASS, ln(1 - p) for FAIL, with p clipped to [0.001, 0.999]. Higher is better;
              ln(0.5) = -0.693 is the coin.
  UNTESTABLE verdicts are listed and not scored: no outcome exists to score against.
  Quantities: inside [lo, hi] or not; log10 ratio of outcome to point when both have the same sign
  and are non-zero (|ratio| 1 is a factor of 10); absolute error always.
"""
import math

from .verdict import get

CLIP = 1e-3


def problems(fc, verdict_names):
    out = []
    if not isinstance(fc, dict):
        return ["forecasts: must be an object with 'verdicts' and/or 'quantities'"]
    for name, p in (fc.get("verdicts") or {}).items():
        if name not in verdict_names:
            out.append(f"forecasts.verdicts.{name}: no such verdict")
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
            out.append(f"forecasts.verdicts.{name}: a probability in [0, 1]")
    for path, q in (fc.get("quantities") or {}).items():
        if not isinstance(q, dict) or not isinstance(q.get("point"), (int, float)):
            out.append(f"forecasts.quantities.{path}: needs a numeric point")
        elif ("lo" in q) != ("hi" in q) or ("lo" in q and not q["lo"] <= q["point"] <= q["hi"]):
            out.append(f"forecasts.quantities.{path}: lo <= point <= hi, both or neither")
    return out


def brier(p, o):
    return (p - o) ** 2


def log_score(p, o):
    p = min(1 - CLIP, max(CLIP, p))
    return math.log(p if o else 1 - p)


def score(fc, result):
    """Scores for a judged result. Returns None when the spec has no forecasts."""
    if not fc:
        return None
    rows, untestable = [], []
    for name, p in (fc.get("verdicts") or {}).items():
        v = result["verdicts"].get(name, {}).get("verdict")
        if v not in ("PASS", "FAIL"):
            untestable.append(name)
            continue
        o = 1 if v == "PASS" else 0
        rows.append({"verdict": name, "p_pass": p, "outcome": v, "brier": brier(p, o), "log_score": log_score(p, o)})
    qrows = []
    for path, q in (fc.get("quantities") or {}).items():
        try:
            got = get(result, path)
        except (KeyError, IndexError, ValueError):
            qrows.append({"quantity": path, "point": q["point"], "got": None, "why": "missing"})
            continue
        row = {"quantity": path, "point": q["point"], "got": got, "abs_error": abs(got - q["point"])}
        if "lo" in q:
            row["inside"] = bool(q["lo"] <= got <= q["hi"])
        if got and q["point"] and (got > 0) == (q["point"] > 0):
            row["log10_ratio"] = math.log10(got / q["point"])
        qrows.append(row)
    n = len(rows)
    summary = {"n_scored": n, "untestable_not_scored": untestable,
               "mean_brier": (math.fsum(r["brier"] for r in rows) / n) if n else None,
               "mean_log_score": (math.fsum(r["log_score"] for r in rows) / n) if n else None}
    inside = [r["inside"] for r in qrows if "inside" in r]
    if inside:
        summary["interval_coverage"] = sum(inside) / len(inside)
        summary["n_intervals"] = len(inside)
    ratios = [abs(r["log10_ratio"]) for r in qrows if "log10_ratio" in r]
    if ratios:
        summary["median_abs_log10_ratio"] = sorted(ratios)[len(ratios) // 2] if len(ratios) % 2 else \
            (sorted(ratios)[len(ratios) // 2 - 1] + sorted(ratios)[len(ratios) // 2]) / 2
    return {"verdicts": rows, "quantities": qrows, "summary": summary}


def ledger_line(sc):
    s = sc["summary"]
    parts = []
    if s["n_scored"]:
        parts.append(f"Brier {s['mean_brier']:.3f} and log score {s['mean_log_score']:.3f} over {s['n_scored']} verdicts"
                     " (coin: 0.250 and -0.693)")
    if s["untestable_not_scored"]:
        parts.append("not scored, untestable: " + ", ".join(s["untestable_not_scored"]))
    if "interval_coverage" in s:
        parts.append(f"{s['interval_coverage']:.2f} of {s['n_intervals']} quantity intervals cover the outcome")
    if "median_abs_log10_ratio" in s:
        parts.append(f"median quantity miss a factor of {10 ** s['median_abs_log10_ratio']:.2f}")
    return "; ".join(parts) + "." if parts else "no forecast could be scored."
