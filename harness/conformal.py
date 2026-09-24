"""Split-conformal LAC prediction sets for the decide lane's choice families.

LAC (least ambiguous set-valued classifier) scores a labelled calibration row by
``1 - p(true label)``. The conformal quantile of those scores, ``qhat``, gives
the prediction set ``{y : 1 - p(y) <= qhat}`` for a new row.

Mondrian grouping keeps one quantile per (family, class), so the coverage
statement holds per class. A class with too few calibration rows for the
requested level gets ``qhat = 1.0``, which puts that class in every set; the
policy then abstains on set size rather than acting on thin evidence.

Guarantee, and its limit: when calibration and test rows are exchangeable, the
marginal coverage ``P(true label in set)`` is at least ``1 - alpha``; Mondrian
sets hold that per class under within-class exchangeability. Neither holds
under distribution shift, and neither says anything about a single decision.
This module is stdlib only and calls no model.
"""
from __future__ import annotations

import math

DOES_NOT_PROVE = (
    "Coverage holds only when calibration and future rows are exchangeable "
    "(per class for Mondrian sets); it fails under shift and says nothing "
    "about any single decision.")
_SUM_TOLERANCE = 1e-6


def _alpha(value: object) -> float:
    if type(value) not in (int, float) or not 0 < value < 1:
        raise ValueError("alpha must be a number strictly between 0 and 1")
    return float(value)


def _probabilities(probabilities: object) -> dict:
    """A validated copy of a finite, normalized label distribution."""
    if type(probabilities) is not dict or not probabilities:
        raise ValueError("probabilities must be a non-empty dict")
    out = {}
    for label, value in probabilities.items():
        if type(label) is not str or not label:
            raise ValueError("probability labels must be non-empty strings")
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("probabilities must be finite numbers in [0, 1]")
        out[label] = float(value)
    if abs(math.fsum(out.values()) - 1.0) > _SUM_TOLERANCE:
        raise ValueError("probabilities must sum to one")
    return out


def lac_score(probabilities: dict, label: str) -> float:
    """Nonconformity of ``label``: one minus its probability (1.0 when absent)."""
    probs = _probabilities(probabilities)
    if type(label) is not str or not label:
        raise ValueError("label must be a non-empty string")
    return 1.0 - probs.get(label, 0.0)


def lac_quantile(scores: list, alpha: float) -> float:
    """The split-conformal quantile: the ceil((n+1)(1-alpha))-th smallest score.

    When that rank exceeds n, the finite-sample quantile is infinite; 1.0 is
    returned instead, which admits every label and keeps the value JSON-safe.
    """
    alpha = _alpha(alpha)
    if type(scores) is not list or not scores:
        raise ValueError("scores must be a non-empty list")
    for score in scores:
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("scores must be finite numbers in [0, 1]")
    n = len(scores)
    # Rounding first keeps an exact integer product from ceiling up by float noise.
    rank = math.ceil(round((n + 1) * (1 - alpha), 9))
    if rank > n:
        return 1.0
    return float(sorted(scores)[rank - 1])


def _label_qhat(qhat: object, label: str) -> float:
    if type(qhat) is dict:
        value = qhat.get(label, 1.0)  # an unseen class is admitted, never dropped
    else:
        value = qhat
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("qhat must be a number in [0, 1] or a dict of them")
    return float(value)


def prediction_set(probabilities: dict, qhat: float | dict) -> list[str]:
    """Labels whose LAC score is within ``qhat``, most probable first.

    ``qhat`` is one quantile for every label, or a Mondrian dict mapping each
    class to its own quantile.
    """
    probs = _probabilities(probabilities)
    kept = [label for label, p in probs.items() if 1.0 - p <= _label_qhat(qhat, label)]
    return sorted(kept, key=lambda label: (-probs[label], label))


def _row(row: object) -> tuple[str, str, float]:
    if type(row) is not dict or "probabilities" not in row or "target" not in row:
        raise ValueError("a conformal row needs probabilities and a target")
    family = row.get("family", "")
    if type(family) is not str:
        raise ValueError("family must be a string")
    return family, row["target"], lac_score(row["probabilities"], row["target"])


def split_quantile(rows: list, alpha: float) -> float:
    """One marginal quantile over every row, ignoring family and class."""
    if type(rows) is not list or not rows:
        raise ValueError("rows must be a non-empty list")
    return lac_quantile([_row(row)[2] for row in rows], alpha)


def mondrian_quantiles(rows: list, alpha: float) -> dict:
    """Per-family, per-class quantiles: ``{family: {class: qhat}}``.

    Each row is ``{"probabilities", "target", "family"?}``; a missing family is
    the empty string. The class is the row's target label.
    """
    if type(rows) is not list or not rows:
        raise ValueError("rows must be a non-empty list")
    alpha = _alpha(alpha)
    groups: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        family, target, score = _row(row)
        groups.setdefault(family, {}).setdefault(target, []).append(score)
    return {family: {label: lac_quantile(scores, alpha)
                     for label, scores in sorted(classes.items())}
            for family, classes in sorted(groups.items())}


def coverage(rows: list, qhat: float | dict) -> dict:
    """Empirical coverage and mean set size of ``qhat`` on labelled rows."""
    if type(rows) is not list or not rows:
        raise ValueError("rows must be a non-empty list")
    covered, sizes = 0, 0
    for row in rows:
        _row(row)
        members = prediction_set(row["probabilities"], qhat)
        covered += row["target"] in members
        sizes += len(members)
    return {"n": len(rows), "covered": covered, "coverage": covered / len(rows),
            "mean_set_size": sizes / len(rows), "does_not_prove": DOES_NOT_PROVE}
