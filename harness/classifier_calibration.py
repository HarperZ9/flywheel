"""Offline probability scaling and bounded-risk threshold diagnostics.

These fits never authorize actions. Their statistical interpretation requires
independent representative cases and a frozen model; synthetic tests cannot
establish deployment risk. Temperature and threshold fits need separate data.
"""
from __future__ import annotations

import math

from .evidence_json import canonical_sha256

ABSTAIN = "__abstain__"


def _number(value: object, low: float, high: float) -> float:
    if type(value) not in (int, float):
        raise ValueError("invalid numeric input")
    try:
        out = float(value)
    except OverflowError as exc:
        raise ValueError("invalid numeric input") from exc
    if not math.isfinite(out) or not low <= out <= high:
        raise ValueError("invalid numeric input")
    return out


def scale_distribution(probabilities: dict, temperature: float) -> dict:
    """Scale finite normalized probabilities without reviving masked zeros."""
    temperature = _number(temperature, .01, 100)
    if type(probabilities) is not dict or not 1 <= len(probabilities) <= 51:
        raise ValueError("invalid probability distribution")
    if any(type(key) is not str or not key for key in probabilities):
        raise ValueError("invalid probability key")
    probs = {key: _number(value, 0, 1) for key, value in probabilities.items()}
    if abs(math.fsum(probs.values()) - 1) > 1e-8:
        raise ValueError("probabilities must sum to one")
    logs = {key: math.log(p) / temperature for key, p in probs.items() if p > 0}
    peak = max(logs.values())
    numerators = {key: math.exp(logs[key]-peak) if key in logs else 0 for key in probs}
    denominator = math.fsum(numerators.values())
    return {key: value / denominator for key, value in numerators.items()}


def _rows(cases: list[dict]) -> list[dict]:
    if type(cases) is not list or not 1 <= len(cases) <= 100_000:
        raise ValueError("invalid calibration cases")
    rows = []
    for case in cases:
        required = {"probabilities", "target_choice_ids"}
        identity = {"case_id", "source_group", "input_sha256", "label_kind"}
        if type(case) is not dict or set(case) not in (required, required | identity):
            raise ValueError("invalid calibration case")
        probs = scale_distribution(case["probabilities"], 1)
        targets = case["target_choice_ids"]
        if type(targets) is not list or any(type(t) is not str for t in targets):
            raise ValueError("invalid calibration targets")
        if ABSTAIN not in probs or ABSTAIN in targets:
            raise ValueError("invalid abstention class")
        if len(set(targets)) != len(targets) or any(t not in probs for t in targets):
            raise ValueError("invalid calibration targets")
        rows.append({"probabilities": probs, "targets": targets or [ABSTAIN]})
    return rows


def _outcome_units(cases: list[dict]) -> str:
    """A declared unit is required; declaring it does not establish independence."""
    ids, groups, inputs = set(), set(), set()
    for case in cases:
        if "case_id" not in case:
            return "missing_outcome_identity"
        for key in ("case_id", "source_group", "input_sha256", "label_kind"):
            if type(case[key]) is not str or not 1 <= len(case[key]) <= 256:
                raise ValueError("invalid outcome identity")
        digest = case["input_sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid outcome input hash")
        if case["case_id"] in ids or case["source_group"] in groups or digest in inputs:
            raise ValueError("duplicate or correlated outcome units")
        ids.add(case["case_id"])
        groups.add(case["source_group"])
        inputs.add(digest)
        if case["label_kind"] not in {"human_reviewed", "verified_outcome"}:
            return "unverified_outcome_labels"
    return "declared_independent_outcome_units"


def _loss(rows: list[dict], temperature: float) -> float:
    loss = 0.0
    for row in rows:
        probs = scale_distribution(row["probabilities"], temperature)
        mass = math.fsum(probs[key] for key in row["targets"])
        loss -= math.log(max(mass, 1e-15))
    return loss / len(rows)


def fit_temperature(cases: list[dict]) -> dict:
    """Fit a fixed positive temperature grid on the temperature split only."""
    rows = _rows(cases)
    grid = [2 ** (index / 8) for index in range(-24, 33)]
    chosen = min(grid, key=lambda t: (_loss(rows, t), abs(math.log(t))))
    return {
        "status": "diagnostic_fit", "temperature": chosen,
        "raw_log_loss": _loss(rows, 1), "fitted_log_loss": _loss(rows, chosen),
        "calibration_examples": len(rows), "input_sha256": canonical_sha256(cases),
        "does_not_prove": "Calibration on unseen workflow outcomes or authority to select.",
    }


def _binomial_cdf(errors: int, n: int, p: float) -> float:
    if p >= 1:
        return float(errors == n)
    if p <= 0:
        return 1.0
    logs = [math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)
            + k*math.log(p)+(n-k)*math.log1p(-p) for k in range(errors+1)]
    peak = max(logs)
    return math.exp(peak) * math.fsum(math.exp(x-peak) for x in logs)


def _upper(errors: int, n: int, alpha: float) -> float:
    if not n or errors == n:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(alpha)/n)
    low, high = errors/n, 1.0
    for _ in range(55):
        mid = (low+high)/2
        if _binomial_cdf(errors, n, mid) > alpha:
            low = mid
        else:
            high = mid
    return high


def select_threshold(cases: list[dict], *, thresholds: list[float] | None = None,
                     max_error: float = .05, alpha: float = .05) -> dict:
    """Fixed-grid Bonferroni/Clopper-Pearson threshold screening.

    The grid must be fixed before inspecting these labels. Input probabilities
    must use a frozen temperature fit on other examples. Bounds assume iid data,
    and are conditional on selection; correlated generated cases do not satisfy
    that assumption simply because their text differs.
    """
    rows = _rows(cases)
    unit_status = _outcome_units(cases)
    max_error = _number(max_error, 0, 1)
    alpha = _number(alpha, 1e-12, .5)
    grid = thresholds if thresholds is not None else [.5, .6, .7, .8, .9, .95, .99]
    if type(grid) is not list or not 1 <= len(grid) <= 100:
        raise ValueError("invalid threshold grid")
    grid = sorted(set(_number(t, 0, 1) for t in grid))
    predictions = []
    for row in rows:
        probs = row["probabilities"]
        peak = max(probs.values())
        winners = [key for key, value in probs.items() if value == peak]
        # A tied choice does not become an arbitrary decision by dictionary order.
        choice = winners[0] if len(winners) == 1 else ABSTAIN
        predictions.append((choice, peak, choice in row["targets"]))
    candidates = []
    for threshold in grid:
        selected = [r for r in predictions if r[0] != ABSTAIN and r[1] >= threshold]
        n, errors = len(selected), sum(not r[2] for r in selected)
        candidates.append({"threshold": threshold, "selected": n, "errors": errors,
                           "coverage": n/len(rows), "error_rate": errors/n if n else None,
                           "upper_error_bound": _upper(errors, n, alpha/len(grid))})
    passed = [r for r in candidates if r["selected"] and r["upper_error_bound"] <= max_error
              and unit_status == "declared_independent_outcome_units"]
    winner = max(passed, key=lambda r: r["selected"]) if passed else None
    return {
        "status": "statistical_candidate_only" if winner else "insufficient_risk_evidence",
        "threshold": winner["threshold"] if winner else None,
        "requires_independent_outcome_validation": True,
        "outcome_unit_status": unit_status,
        "calibration_examples": len(rows), "max_error": max_error, "alpha": alpha,
        "bound": "one-sided Clopper-Pearson with fixed-grid Bonferroni correction",
        "candidates": candidates, "input_sha256": canonical_sha256(cases),
        "does_not_prove": "Representative data, iid cases, deployment safety, or authorization.",
    }
