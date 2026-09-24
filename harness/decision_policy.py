"""Policy cards for the decide lane: fit on labelled rows, apply to readouts.

A reading is one question's readout: ``{"type", "raw", "order_agreement",
"label_mass"}`` plus optional ``"eligible"`` (a label mask) and ``"code_gate"``
(a reason the caller already decided in code). ``raw`` maps the real labels and
the none label (``none`` for noul, ``__none__`` otherwise) to probabilities.

``apply`` runs the gates in a fixed order, and the first failure names the
abstention: code gates, format (label mass), order agreement, none, exclusive
noul invariants, card status, the act gate, then the conformal set for choice
questions. ``correct_prob`` is the only value a threshold reads: the top real
probability after the none mass is removed and the frozen temperature applied.

``fit_card`` fits temperature on development rows only and refuses any other
split there, freezes it, folds each calibration unit into the shape
``select_threshold`` screens (probability ``q`` on the act value when the unit
would act, else 0; target the act value only when acting is right), checks the
feasibility floor ``(mu - alpha)/(1 - alpha)``, and fits Mondrian conformal
quantiles for choice families. ``_screen_acts`` mirrors the screen's selection
rule exactly, so the units the card certifies are the units ``apply`` acts on.
Fitting and revocation live in ``decision_policy_fit`` to keep each file under
the 300-line gate; ``fit_card`` here forwards to it.

A card is evidence for one family and period. It does not prove correctness of
any decision, authorization, or exchangeability of future items, and a mode of
``shadow`` or ``advise`` is enforced by the caller, not here.
"""
from __future__ import annotations

import math

from . import conformal
from .classifier_calibration import ABSTAIN, scale_distribution
from .evidence_json import canonical_sha256
from .systemone_contract import NONE_LABEL, NOUL_NONE

CARD_SCHEMA = "flywheel.decision-policy-card/v1"
DEFAULT_GRID = [.5, .6, .7, .8, .9, .95, .99]
P_NONE_MAX = 0.5
INVARIANT_SUM_MAX = 1.05
LABEL_MASS_PERCENTILE = 0.01
CV_FOLDS = 5
TYPES = ("noul", "choice", "score")
STATUSES = ("uncalibrated", "insufficient_risk_evidence", "infeasible_at_alpha",
            "statistical_candidate_only", "confirmed", "revoked")
ACTING_STATUSES = ("statistical_candidate_only", "confirmed")
CLASS_BOUNDS = {"advisory": 0.10, "reversible": 0.05}  # destructive never acts here
PRE_READ_REASONS = ("code_gate", "sensitivity_refused", "backend_capability",
                    "backend_unavailable", "deadline")
IDENTITY = ("case_id", "source_group", "input_sha256", "label_kind")
DOES_NOT_PROVE = ("Correctness of any single decision, authorization, or "
                  "exchangeability of future items.")


def new_card(meta: dict | None = None, *, act_on: list | None = None) -> dict:
    """An ``uncalibrated`` card: every decision abstains, shadow evidence only."""
    meta = meta or {}
    return {
        "schema": CARD_SCHEMA, "family": meta.get("family"),
        "backend_id": meta.get("backend_id"), "model_id": meta.get("model_id"),
        "weights_sha256": meta.get("weights_sha256"), "question_type": meta.get("question_type", "noul"),
        "temperature": 1.0, "temperature_applied": False, "temperature_fit_input_sha256": None,
        "label_mass_min": 0.0, "threshold": None, "threshold_field": "correct_prob",
        "threshold_grid": list(DEFAULT_GRID), "correct_prob_source": "zero_shot_top_probability",
        "conformal_qhat": None, "alpha": None, "delta": None, "max_error": None,
        "action_class": meta.get("action_class", "reversible"), "act_on": act_on,
        "feasibility_floor": None, "calibration_input_sha256": None, "sealed_confirm": None,
        "bench_receipt_sha256": None, "status": "uncalibrated", "revoked_reason": None,
        "valid_until": meta.get("valid_until"), "does_not_prove": DOES_NOT_PROVE}


def _check_reading(reading: object) -> None:
    ok = (type(reading) is dict and reading.get("type") in TYPES
          and type(reading.get("raw")) is dict and reading["raw"]
          and type(reading.get("order_agreement")) is bool
          and type(reading.get("label_mass")) in (int, float)
          and 0 <= reading["label_mass"] <= 1)
    if ok:
        values = list(reading["raw"].values())
        ok = all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values)
        ok = ok and abs(math.fsum(values) - 1) <= 1e-6
    if not ok:
        raise ValueError("invalid reading")


def _scale(probs: dict, temperature: float) -> dict:
    """Temperature scaling as in classifier_calibration, without its label cap."""
    if temperature == 1.0:
        return dict(probs)
    logs = {k: math.log(p) / temperature for k, p in probs.items() if p > 0}
    peak = max(logs.values())
    nums = {k: math.exp(logs[k] - peak) if k in logs else 0.0 for k in probs}
    total = math.fsum(nums.values())
    return {k: v / total for k, v in nums.items()}


def _view(reading: dict, temperature: float) -> dict:
    """The scored view: eligible real labels renormalized without none, then scaled.

    ``full`` keeps the none label beside the real ones for conformal sets.
    """
    none = NOUL_NONE if reading["type"] == "noul" else NONE_LABEL
    mask = reading.get("eligible")
    real = {k: float(v) for k, v in reading["raw"].items()
            if k != none and (mask is None or k in mask)}
    p_none = float(reading["raw"].get(none, 0.0))
    mass = math.fsum(real.values())
    view = {"p_none": p_none, "n_real": len(real), "real": None, "best": None, "q": 0.0,
            "none_top": p_none >= P_NONE_MAX or not real or p_none >= max(real.values())}
    if mass > 0:
        view["real"] = _scale({k: v / mass for k, v in real.items()}, temperature)
        view["best"] = min(view["real"], key=lambda k: (-view["real"][k], k))
        view["q"] = view["real"][view["best"]]
        full = {**real, none: p_none}
        total = math.fsum(full.values())
        view["full"] = _scale({k: v / total for k, v in full.items()}, temperature)
    return view


def _gates(reading: dict, label_mass_min: float, temperature: float) -> tuple:
    """Gates 1 to 4 for one reading: (first failing reason or None, view)."""
    _check_reading(reading)
    view = _view(reading, temperature)
    if reading.get("code_gate") is not None:
        if reading["code_gate"] not in PRE_READ_REASONS:
            raise ValueError("unknown code gate reason")
        return reading["code_gate"], view
    if reading.get("eligible") is not None and not view["n_real"]:
        return "code_gate", view  # the caller's mask left no real option
    if reading["label_mass"] < label_mass_min:
        return "format", view
    if not reading["order_agreement"]:
        return "order_disagreement", view
    if view["none_top"] or view["real"] is None:
        return "none_top", view
    return None, view


def _screen_acts(q: float, threshold: float) -> bool:
    """True exactly when select_threshold would select a unit folded with ``q``."""
    if q <= 0:
        return False
    probs = scale_distribution({"act": q, ABSTAIN: 1.0 - q}, 1)
    return probs["act"] > probs[ABSTAIN] and probs["act"] >= threshold


def _act_values(card: dict, act_on: dict | None, qid: str) -> list:
    requested = (act_on or {}).get(qid)
    if card["act_on"] is None:
        return list(requested or [])
    if requested is None:
        return list(card["act_on"])
    return [v for v in card["act_on"] if v in requested]  # a request only narrows


def _invariant_hits(views: dict, readings: dict, invariants) -> set:
    """Ids in an exclusive noul pair whose none-free, frozen-temperature true
    probabilities sum above ``INVARIANT_SUM_MAX``."""
    hits = set()
    for pair in invariants:
        if (type(pair) not in (list, tuple) or len(pair) != 2 or pair[0] == pair[1]
                or any(q not in readings or readings[q]["type"] != "noul" for q in pair)):
            raise ValueError("an invariant is a pair of distinct noul question ids")
        both = [views[q]["real"] for q in pair]
        if all(both) and both[0].get("true", 0) + both[1].get("true", 0) > INVARIANT_SUM_MAX:
            hits.update(pair)
    return hits


def _card_reason(card: dict, now: str | None) -> str | None:
    if card["status"] not in ACTING_STATUSES:
        return card["status"]
    if now is not None and card.get("valid_until") and now > card["valid_until"]:
        return "uncalibrated"  # the certified period has ended; re-certify first
    return None


def _decision(reading: dict, view: dict, reason: str | None, pset) -> dict:
    return {"action": "abstain" if reason else "act", "reason": reason,
            "argmax": view["best"], "raw": dict(reading["raw"]), "p_none": view["p_none"],
            "correct_prob": view["q"], "order_agreement": reading["order_agreement"],
            "label_mass": reading["label_mass"], "prediction_set": pset}


def _late_gates(card: dict, view: dict, reading: dict, values: list, now) -> tuple:
    """Gates 6 to 8: card status, act, conformal. Returns (reason, set, would_act_at)."""
    pset = None
    if reading["type"] == "choice" and card["conformal_qhat"] is not None and view["real"]:
        pset = conformal.prediction_set(view["full"], card["conformal_qhat"])
    reason = _card_reason(card, now)
    if reason is not None:
        grid = card.get("threshold_grid") or DEFAULT_GRID
        acts = view["best"] in values
        return reason, pset, [t for t in grid if acts and _screen_acts(view["q"], t)]
    if view["best"] not in values or not _screen_acts(view["q"], card["threshold"]):
        return "below_threshold", pset, None
    if pset is not None and len(pset) > 1:
        return "set_size_gt_1", pset, None
    return None, pset, None


def _check_card(card: dict) -> None:
    if (type(card) is not dict or card.get("schema") != CARD_SCHEMA
            or card.get("status") not in STATUSES
            or card.get("threshold_field") != "correct_prob"
            or (card["status"] in ACTING_STATUSES and card.get("threshold") is None)):
        raise ValueError("invalid policy card")


def apply(card: dict | None, readings: dict, *, act_on: dict | None = None,
          invariants=(), now: str | None = None) -> dict:
    """Decide act or abstain for each question id in ``readings``.

    ``act_on`` (question id to act values) may only narrow the card's act
    values. ``invariants`` lists exclusive noul pairs. ``now`` is an ISO date
    compared with the card's ``valid_until``.
    """
    card = new_card() if card is None else card
    _check_card(card)
    if type(readings) is not dict:
        raise ValueError("readings must map question ids to readings")
    early ={qid: _gates(r, card["label_mass_min"], card["temperature"])
             for qid, r in readings.items()}
    views = {qid: pair[1] for qid, pair in early.items()}
    hits = _invariant_hits(views, readings, invariants)
    out = {}
    for qid, (reason, view) in early.items():
        reading, pset, would = readings[qid], None, None
        if reason is None and qid in hits:
            reason = "invariant_violation"
        if reason is None:
            values = _act_values(card, act_on, qid)
            reason, pset, would = _late_gates(card, view, reading, values, now)
        out[qid] = _decision(reading, view, reason, pset)
        if would is not None:
            out[qid]["would_act_at"] = would
    return out


def fold_unit(row: dict, *, temperature: float, label_mass_min: float, act_on: list) -> dict:
    """One calibration unit in the select_threshold shape (see module docstring)."""
    reason, view = _gates(row["reading"], label_mass_min, temperature)
    acts = reason is None and view["best"] in act_on
    act_value = view["best"] if acts else act_on[0]
    q = view["q"] if acts else 0.0
    case = {"probabilities": {act_value: q, ABSTAIN: 1.0 - q},
            "target_choice_ids": [act_value] if row["target"] == act_value else []}
    case.update({key: row[key] for key in IDENTITY if key in row})
    return case


def feasibility_floor(mu: float, alpha: float) -> float:
    """The least abstention share that can reach risk ``alpha`` from error ``mu``."""
    if not 0 <= mu <= 1 or not 0 < alpha < 1:
        raise ValueError("mu must lie in [0, 1] and alpha in (0, 1)")
    return max(0.0, (mu - alpha) / (1 - alpha))


def feasibility(folded: list, *, alpha: float, min_useful_coverage: float) -> dict:
    """Base error ``mu`` of the would-act units at full coverage, and the floor.

    ``max_act_share`` is an optimistic bound: the would-act units left after the
    floor, as a share of units whose true answer is an act value.
    """
    def act_key(case):
        return next(k for k in case["probabilities"] if k != ABSTAIN)
    acts = [c for c in folded if c["probabilities"][act_key(c)] > 0]
    wrong = sum(act_key(c) not in c["target_choice_ids"] for c in acts)
    targets = sum(bool(c["target_choice_ids"]) for c in folded)
    mu = wrong / len(acts) if acts else None
    floor = feasibility_floor(mu, alpha) if acts else None
    share = min(1.0, (1 - floor) * len(acts) / targets) if acts and targets else 0.0
    return {"mu": mu, "floor": floor, "would_act_units": len(acts),
            "act_target_units": targets, "max_act_share": share,
            "min_useful_coverage": min_useful_coverage,
            "feasible": share >= min_useful_coverage}


def card_sha256(card: dict) -> str:
    """The canonical digest a response names as ``policy_card_sha256``."""
    return canonical_sha256(card)


def fit_card(dev_rows: list, calibration_rows: list, **kwargs) -> dict:
    """Fit a card; see ``decision_policy_fit.fit_card`` (split for the file gate)."""
    from .decision_policy_fit import fit_card as _fit
    return _fit(dev_rows, calibration_rows, **kwargs)
