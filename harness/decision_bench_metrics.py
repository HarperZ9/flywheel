"""Decision bench metrics over scored rows (``decision_backends.read_items``).
A row's ``raw`` maps its real ``labels`` and its ``none_label`` to
probabilities, or is None when its unit's read failed. ``correct_prob``, the
only value a threshold reads, is the top real-label probability with the none
mass removed, renormalized, after an optional frozen temperature. ``view``
applies the gates a noul family needs in the design order (format, order,
none, act, the screen's threshold rule) and mirrors ``decision_policy.apply``
for noul questions without invariants; a test holds the two equal. It proves
no label true and no unit independent; the bounds assume independent units.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from itertools import groupby

from .classifier_calibration import ABSTAIN, scale_distribution, select_threshold
from .classifier_calibration import _upper as clopper_pearson_upper
from .classifier_metrics import evaluate_probability_cases
from .decision_contract import ID_PATTERN

CERTIFIED = "statistical_candidate_only"
NONE_GATE = 0.5
DEFAULT_GRID = (.5, .6, .7, .8, .9, .95, .99)
SPLIT_ORDER = ("development", "calibration", "sealed")
SHINGLE_WORDS, LEAK_CONTAINMENT, LEAK_MAX_SHARE = 8, 0.5, 0.02


def _probs(row: dict, temperature: float) -> dict:
    raw = row["raw"]
    return raw if temperature == 1.0 else scale_distribution(raw, temperature)


def _gate(row, pred, p_none, top_raw, cp, act_on, threshold, mass_floor):
    if mass_floor is not None and row["label_mass"] < mass_floor:
        return "format"
    if row["order_agreement"] is False:
        return "order_disagreement"
    if p_none >= NONE_GATE or p_none >= top_raw:
        return "none_top"
    if pred is None:
        return "tie"
    if pred not in act_on:
        return "not_act"
    # The screen's rule: the act must beat abstention and reach the threshold.
    if threshold is not None and not (cp > 1.0 - cp and cp >= threshold):
        return "below_threshold"
    return None


def view(row: dict, act_on, *, threshold=None, temperature: float = 1.0,
         mass_floor=None) -> dict:
    """One row's decision: ``acts`` only when every gate passes, else
    ``reason`` names the first gate that failed."""
    if row["raw"] is None:
        return {"pred": None, "correct_prob": None, "p_none": None, "acts": False,
                "correct": False, "reason": row.get("error_type") or "backend_unavailable"}
    p_none = row["raw"].get(row["none_label"], 0.0)   # the none gate reads raw mass
    top_raw = max(row["raw"].get(k, 0.0) for k in row["labels"])
    probs = _probs(row, temperature)
    real = {k: probs.get(k, 0.0) for k in row["labels"]}
    top, mass = max(real.values()), math.fsum(real.values())
    winners = [k for k, v in real.items() if v == top]
    pred = winners[0] if len(winners) == 1 and mass > 0 else None
    cp = top / mass if pred is not None else 0.0
    reason = _gate(row, pred, p_none, top_raw, cp, act_on, threshold, mass_floor)
    return {"pred": pred, "correct_prob": cp, "p_none": p_none,
            "acts": reason is None, "correct": pred == row["target"],
            "reason": reason}


def fold(rows: list, views: list, act_on) -> list[dict]:
    """Fold certification units into ``select_threshold`` cases: probabilities
    ``{act: q, __abstain__: 1 - q}`` with q = correct_prob when the unit passed
    its gates with an act-label argmax, else 0; targets ``[act]`` when acting
    was right, else ``[]``. So a unit is selected only when it would act, and
    is an error only when that act was wrong. At q = 0.5 the screen abstains."""
    cases = []
    for row, v in zip(rows, views):
        if not row["certification_unit"]:
            continue
        act = v["pred"] if v["pred"] in act_on else act_on[0]
        q = v["correct_prob"] if v["acts"] else 0.0
        cases.append({
            "probabilities": {act: q, ABSTAIN: 1.0 - q},
            "target_choice_ids": [act] if row["target"] == act else [],
            "case_id": row["item_id"], "source_group": row["unit_id"],
            "input_sha256": row["input_sha256"], "label_kind": row["label_kind"]})
    return cases


def certify(rows: list, act_on, *, max_error: float = .05, delta: float = .05,
            grid=None, temperature: float = 1.0, mass_floor=None) -> dict:
    """Run the existing Bonferroni and Clopper-Pearson screen on the fold."""
    views = [view(r, act_on, temperature=temperature, mass_floor=mass_floor)
             for r in rows]
    cases = fold(rows, views, act_on)
    if not cases:
        return {"status": "insufficient_risk_evidence", "threshold": None, "units": 0}
    result = select_threshold(cases, thresholds=list(grid or DEFAULT_GRID),
                              max_error=max_error, alpha=delta)
    return {**result, "units": len(cases)}


def selective_risk(rows: list, views: list, act_on, *, delta: float = .05) -> dict:
    """Errors among acted decisions, with an unadjusted one-sided bound."""
    acted = [v for v in views if v["acts"]]
    errors = sum(1 for v in acted if not v["correct"])
    should_act = [v for r, v in zip(rows, views) if r["target"] in act_on]
    should_keep = [v for r, v in zip(rows, views) if r["target"] not in act_on]
    n = len(acted)
    return {
        "items": len(rows), "acted": n, "errors": errors,
        "error_rate": errors / n if n else None,
        "upper_error_bound": clopper_pearson_upper(errors, n, delta),
        "coverage": n / len(rows) if rows else None,
        "act_recall": (sum(1 for v in should_act if v["acts"]) / len(should_act)
                       if should_act else None),
        "keep_recall": (sum(1 for v in should_keep if not v["acts"])
                        / len(should_keep) if should_keep else None),
        "tokens_excluded": sum(r["tokens"] for r, v in zip(rows, views) if v["acts"]),
        "tokens_total": sum(r["tokens"] for r in rows),
    }


def aurc(views: list, item_ids: list) -> float | None:
    """Area under the risk-coverage curve, ranked by correct_prob."""
    scored = sorted(((v["correct_prob"], i, v["correct"])
                     for v, i in zip(views, item_ids) if v["pred"] is not None),
                    key=lambda t: (-t[0], t[1]))
    errors, total = 0, 0.0
    for k, (_, _, ok) in enumerate(scored, 1):
        errors += not ok
        total += errors / k
    return total / len(scored) if scored else None


def auroc(rows: list, positive: str = "true") -> float | None:
    """Rank AUROC of the renormalized positive-label probability, ties averaged."""
    scored = []
    for r in rows:
        if r["raw"] is None or positive not in r["labels"]:
            continue
        mass = math.fsum(r["raw"].get(k, 0.0) for k in r["labels"])
        score = r["raw"].get(positive, 0.0) / mass if mass > 0 else 0.0
        scored.append((score, r["target"] == positive))
    pos = sum(1 for _, y in scored if y)
    neg = len(scored) - pos
    if not pos or not neg:
        return None
    rank_sum, start = 0.0, 0
    for _, group in groupby(sorted(scored), key=lambda t: t[0]):
        flags = [y for _, y in group]
        rank_sum += sum(flags) * (2 * start + len(flags) + 1) / 2
        start += len(flags)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def probability_summary(rows: list, *, temperature: float = 1.0) -> dict | None:
    """Brier, log loss, top-1 and 10-bin ECE via evaluate_probability_cases,
    with the none mass as the ``__abstain__`` class."""
    cases = []
    for r in rows:
        if r["raw"] is None or not all(ID_PATTERN.fullmatch(k) for k in r["labels"]):
            continue
        probs = _probs(r, temperature)
        dist = {k: probs.get(k, 0.0) for k in r["labels"]}
        dist[ABSTAIN] = probs.get(r["none_label"], 0.0)
        total = math.fsum(dist.values())
        cases.append({"case_id": r["item_id"], "choice_ids": list(r["labels"]),
                      "target_choice_ids": [r["target"]],
                      "probabilities": {k: v / total for k, v in dist.items()}})
    if not cases:
        return None
    rep = evaluate_probability_cases(cases)
    n = rep["counts"]["probability_observed"]
    ece = math.fsum(b["count"] * abs(b["accuracy"] - b["mean_confidence"])
                    for b in rep["confidence_bins"] if b["count"]) / n
    return {**rep["metrics"], "ece": ece, "cases": n}


def by_unit(rows: list) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(r["unit_id"], []).append(r)
    return groups


def cluster_bootstrap(groups: dict, stat, *, n_boot: int = 1000, seed: int = 1709,
                      level: float = .95) -> dict:
    """Percentile interval from resampling whole units with replacement.
    ``groups`` maps a unit to its payload; ``stat`` maps a list of payloads to
    a number or None, and None draws are dropped and counted."""
    keys = sorted(groups)
    estimate = stat([groups[k] for k in keys]) if keys else None
    rng, draws = random.Random(seed), []
    for _ in range(n_boot if keys else 0):
        value = stat([groups[keys[rng.randrange(len(keys))]] for _ in keys])
        if value is not None:
            draws.append(value)
    draws.sort()
    tail = (1 - level) / 2
    low = draws[math.floor(tail * (len(draws) - 1))] if draws else None
    high = draws[math.ceil((1 - tail) * (len(draws) - 1))] if draws else None
    return {"estimate": estimate, "low": low, "high": high, "level": level,
            "draws": len(draws), "dropped": (n_boot if keys else 0) - len(draws),
            "units": len(keys)}


def shingles(text: str, k: int = SHINGLE_WORDS) -> set:
    """Lower-cased k-word shingles; a shorter non-empty text is one shingle."""
    words = text.lower().split()
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + k]) for i in range(len(words) - k + 1)}


def leak_report(items: list, *, containment: float = LEAK_CONTAINMENT,
                max_share: float = LEAK_MAX_SHARE) -> dict:
    """Flag a unit when more than ``containment`` of its state's shingles occur
    in the union of earlier splits; trip when the flagged share of sealed units
    exceeds ``max_share``."""
    states: dict = {s: {} for s in SPLIT_ORDER}
    for item in items:
        states[item["split"]].setdefault(item["unit_id"], item["state"])
    earlier, report = set(), {}
    for split in SPLIT_ORDER:
        flagged = []
        for unit, state in sorted(states[split].items()):
            sh = shingles(state)
            share = len(sh & earlier) / len(sh) if sh else 0.0
            if earlier and share > containment:
                flagged.append({"unit_id": unit, "containment": round(share, 6)})
        n = len(states[split])
        report[split] = {"units": n, "flagged": len(flagged),
                         "share": len(flagged) / n if n else 0.0,
                         "flagged_units": flagged}
        for state in states[split].values():
            earlier |= shingles(state)
    return {"splits": report, "shingle_words": SHINGLE_WORDS,
            "containment": containment, "max_share": max_share,
            "tripped": report["sealed"]["share"] > max_share}


def per_correct_act(views: list, units: list, *, gpu_rate=None) -> dict:
    """Wall time and cost per correct acted decision (the G3 headline); cost is
    GPU-seconds times a declared rate in dollars per GPU-hour."""
    correct = sum(1 for v in views if v["acts"] and v["correct"])
    wall = math.fsum(u["wall_ms"] for u in units) / 1000
    gpus = [u["gpu_seconds"] for u in units]
    gpu = None if any(g is None for g in gpus) else math.fsum(gpus)
    cost = gpu / 3600 * gpu_rate if gpu is not None and gpu_rate is not None else None
    return {"correct_acts": correct, "wall_seconds": wall,
            "wall_seconds_per_correct_act": wall / correct if correct else None,
            "gpu_seconds": gpu, "rate_per_gpu_hour": gpu_rate,
            "cost_per_correct_act": cost / correct if cost is not None and correct else None}


def percentile(values: list, q: float) -> float | None:
    """Nearest-rank percentile, q in (0, 1]."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else None


def _block(rows, views, act_on, delta, temperature):
    cert = [(r, v) for r, v in zip(rows, views) if r["certification_unit"]]
    return {
        "questions": selective_risk(rows, views, act_on, delta=delta),
        "certification_units": selective_risk([r for r, _ in cert],
                                              [v for _, v in cert], act_on, delta=delta),
        "aurc": aurc(views, [r["item_id"] for r in rows]), "auroc": auroc(rows),
        "probability": probability_summary(rows, temperature=temperature),
    }


def summarize(rows: list, units: list, act_on, *, threshold=None,
              temperature: float = 1.0, mass_floor=None, delta: float = .05,
              gpu_rate=None) -> dict:
    """Per-stratum metrics, abstention reasons, latency and the G3 headline."""
    views = [view(r, act_on, threshold=threshold, temperature=temperature,
                  mass_floor=mass_floor) for r in rows]
    strata = {"all": list(range(len(rows)))}
    for i, r in enumerate(rows):
        if r.get("stratum"):
            strata.setdefault("stratum:" + r["stratum"], []).append(i)
    walls = [u["wall_ms"] for u in units]
    agree = [r["order_agreement"] for r in rows if r["raw"] is not None]
    return {
        "strata": {name: _block([rows[i] for i in idx], [views[i] for i in idx],
                                act_on, delta, temperature)
                   for name, idx in strata.items()},
        "reasons": dict(Counter(v["reason"] or "acted" for v in views)),
        "order_agreement": sum(agree) / len(agree) if agree else None,
        "latency_ms": {"p50": percentile(walls, .5), "p95": percentile(walls, .95)},
        "headline": per_correct_act(views, units, gpu_rate=gpu_rate),
        "backend_errors": sum(1 for u in units if u.get("error_type")),
    }
