"""Fit and revoke decide-lane policy cards.

``fit_card`` takes development rows and calibration rows. Each row is
``{"split", "reading", "target", "case_id", "source_group", "input_sha256",
"label_kind"}``; a calibration unit is the single pre-sampled question of one
commit. The steps run in a fixed order:

1. Split check. Development rows must be tagged ``development`` and calibration
   rows ``calibration``. Anything else, including any ``sealed`` row, is refused,
   and the two splits may share no ``source_group``.
2. Temperature, on development rows only. It is adopted only when grouped
   5-fold cross-validation over source groups lowers held-out log loss;
   otherwise the identity stays. The value is frozen before calibration.
3. ``label_mass_min``: the 1st percentile of development label mass.
4. The fold of each calibration unit (``decision_policy.fold_unit``), the
   feasibility floor, and the fixed-grid Clopper-Pearson screen in
   ``classifier_calibration.select_threshold`` at risk ``alpha`` and
   confidence ``delta``.
5. Mondrian conformal quantiles at miscoverage ``alpha`` for choice families.

``alpha`` may not exceed the action class bound (advisory 0.10, reversible
0.05), stored as ``max_error``. A destructive class never fits. The card is
evidence for one family and period only; the sealed confirm is the bench's job.
"""
from __future__ import annotations

import copy
import math

from . import conformal
from .classifier_calibration import (
    ABSTAIN, _upper, fit_temperature, scale_distribution, select_threshold)
from .decision_policy import (
    CLASS_BOUNDS, CV_FOLDS, DEFAULT_GRID, LABEL_MASS_PERCENTILE, _check_reading,
    _view, feasibility, fold_unit, new_card)
from .evidence_json import canonical_sha256

SPLITS = ("development", "calibration", "sealed")
MIN_USEFUL_COVERAGE = 0.30


def _check_splits(dev_rows: list, calibration_rows: list) -> None:
    for rows, split in ((dev_rows, "development"), (calibration_rows, "calibration")):
        if type(rows) is not list or not rows:
            raise ValueError(f"{split} rows must be a non-empty list")
        for row in rows:
            if type(row) is not dict or not {"reading", "target", "source_group"} <= set(row):
                raise ValueError("a row needs reading, target and source_group")
            if row.get("split") != split:
                tag = row.get("split") if row.get("split") in SPLITS else "unknown"
                stage = "temperature" if split == "development" else "threshold"
                raise ValueError(f"{stage} fitting refuses rows tagged {tag}")
    if {r["source_group"] for r in dev_rows} & {r["source_group"] for r in calibration_rows}:
        raise ValueError("development and calibration rows share a source group")


def _label_mass_min(dev_rows: list) -> float:
    masses = sorted(float(row["reading"]["label_mass"]) for row in dev_rows)
    return masses[max(0, math.ceil(LABEL_MASS_PERCENTILE * len(masses)) - 1)]


def _temperature_cases(dev_rows: list) -> tuple:
    """Development rows as fit_temperature cases over real labels, with groups."""
    cases, groups, excluded = [], [], 0
    for row in dev_rows:
        _check_reading(row["reading"])
        real = _view(row["reading"], 1.0)["real"]
        if real is None or row["target"] not in real or len(real) > 50:
            excluded += 1  # no real mass, target outside the options, or over the fit cap
            continue
        cases.append({"probabilities": {**real, ABSTAIN: 0.0},
                      "target_choice_ids": [row["target"]]})
        groups.append(row["source_group"])
    return cases, groups, excluded


def _held_out_loss(cases: list, temperature: float) -> float:
    total = 0.0
    for case in cases:
        probs = scale_distribution(case["probabilities"], temperature)
        total -= math.log(max(probs[case["target_choice_ids"][0]], 1e-15))
    return total


def choose_temperature(dev_rows: list) -> dict:
    """Grouped 5-fold check, then the full development fit only if it helps."""
    cases, groups, excluded = _temperature_cases(dev_rows)
    if not cases:
        raise ValueError("no development row carries a usable distribution")
    order = sorted(set(groups), key=canonical_sha256)
    fold_of = {group: index % CV_FOLDS for index, group in enumerate(order)}
    fitted = identity = 0.0
    folds = 0
    for fold in range(CV_FOLDS):
        train = [c for c, g in zip(cases, groups) if fold_of[g] != fold]
        test = [c for c, g in zip(cases, groups) if fold_of[g] == fold]
        if not train or not test:
            continue
        fitted += _held_out_loss(test, fit_temperature(train)["temperature"])
        identity += _held_out_loss(test, 1.0)
        folds += 1
    full = fit_temperature(cases)
    adopted = folds >= 2 and fitted < identity
    temperature = full["temperature"] if adopted else 1.0
    return {"temperature": temperature, "temperature_applied": temperature != 1.0,
            "fit_input_sha256": full["input_sha256"], "cv_folds": folds,
            "cv_log_loss_fitted": fitted / len(cases), "cv_log_loss_identity": identity / len(cases),
            "adopted": adopted, "rows_used": len(cases), "rows_excluded": excluded}


def _conformal_qhat(rows: list, temperature: float, alpha: float):
    scored = []
    for row in rows:
        view = _view(row["reading"], temperature)
        if view["real"] is not None:
            scored.append({"probabilities": view["full"], "target": row["target"]})
    return conformal.mondrian_quantiles(scored, alpha)[""] if scored else None


def _check_targets(alpha, delta, act_on, action_class) -> float:
    if action_class not in CLASS_BOUNDS:
        raise ValueError("this action class never acts automatically in this lane")
    bound = CLASS_BOUNDS[action_class]
    if type(alpha) not in (int, float) or not 0 < alpha <= bound:
        raise ValueError("alpha must lie in (0, action class bound]")
    if type(delta) not in (int, float) or not 0 < delta <= .5:
        raise ValueError("delta must lie in (0, 0.5]")
    if type(act_on) is not list or not act_on or not all(
            type(v) is str and v and v != ABSTAIN for v in act_on):
        raise ValueError("act_on must be a non-empty list of labels")
    return bound


def fit_card(dev_rows: list, calibration_rows: list, *, alpha: float, delta: float,
             act_on: list, grid: list | None = None, meta: dict | None = None,
             min_useful_coverage: float = MIN_USEFUL_COVERAGE) -> dict:
    """Fit a ``flywheel.decision-policy-card/v1`` card (see module docstring).

    ``meta`` carries family, backend_id, model_id, weights_sha256,
    question_type, action_class and valid_until.
    """
    meta = dict(meta or {})
    bound = _check_targets(alpha, delta, act_on, meta.get("action_class", "reversible"))
    _check_splits(dev_rows, calibration_rows)
    temp = choose_temperature(dev_rows)
    m_min = _label_mass_min(dev_rows)
    folded = [fold_unit(row, temperature=temp["temperature"], label_mass_min=m_min,
                        act_on=act_on) for row in calibration_rows]
    feas = feasibility(folded, alpha=alpha, min_useful_coverage=min_useful_coverage)
    screen = select_threshold(folded, thresholds=list(DEFAULT_GRID if grid is None else grid),
                              max_error=alpha, alpha=delta)
    card = new_card(meta, act_on=list(act_on))
    card.update({
        "temperature": temp["temperature"], "temperature_applied": temp["temperature_applied"],
        "temperature_fit_input_sha256": temp["fit_input_sha256"], "label_mass_min": m_min,
        "threshold": screen["threshold"] if feas["feasible"] else None,
        "threshold_grid": [c["threshold"] for c in screen["candidates"]],
        "alpha": alpha, "delta": delta, "max_error": bound, "feasibility_floor": feas["floor"],
        "calibration_input_sha256": screen["input_sha256"],
        "status": screen["status"] if feas["feasible"] else "infeasible_at_alpha",
        "fit_report": {"temperature": temp, "feasibility": feas,
                       "outcome_unit_status": screen["outcome_unit_status"],
                       "candidates": screen["candidates"]}})
    if card["question_type"] == "choice":
        card["conformal_qhat"] = _conformal_qhat(calibration_rows, temp["temperature"], alpha)
    return card


def revoke(card: dict, reason: str) -> dict:
    """A revoked copy of ``card``; the family returns to shadow."""
    if type(reason) is not str or not 1 <= len(reason) <= 200:
        raise ValueError("a revocation needs a short reason")
    out = copy.deepcopy(card)
    out["status"], out["revoked_reason"] = "revoked", reason
    return out


def audit_acted(card: dict, *, audited: int, errors: int) -> dict:
    """Re-check acted decisions re-labelled from later outcomes.

    Once ``audited`` reaches the zero-error sample size for ``max_error`` at
    ``delta``, a Clopper-Pearson upper bound above ``max_error`` revokes the
    card. Below that size no bound could pass, so the audit keeps accruing.
    """
    if type(audited) is not int or type(errors) is not int or not 0 <= errors <= audited:
        raise ValueError("errors must be a count within the audited count")
    delta, max_error = card["delta"], card["max_error"]
    minimum = math.ceil(math.log(delta) / math.log1p(-max_error))
    upper = _upper(errors, audited, delta) if audited else 1.0
    revoked = audited >= minimum and upper > max_error
    return {"audited": audited, "errors": errors, "upper_error_bound": upper,
            "minimum_audited": minimum, "revoked": revoked,
            "card": revoke(card, "audit_bound_exceeded") if revoked else copy.deepcopy(card)}
