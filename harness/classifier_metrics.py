"""Probability metrics for classifier decision experiments.

Reports score-distribution quality against caller-supplied independent labels.
It does not assert that the scores are calibrated probabilities.
"""
from __future__ import annotations

import math

from .decision_contract import ID_PATTERN
from .evidence_json import canonical_sha256

SCHEMA = "flywheel.classifier-probability-metrics/v1"
ABSTAIN_ID = "__abstain__"
EPS = 1e-15


class ClassifierMetricError(ValueError):
    """Classifier metric inputs fail closed."""


def _fail(message: str) -> None:
    raise ClassifierMetricError(message)


def _ids(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if type(value) is not list or (not allow_empty and not value):
        _fail(f"invalid {field}")
    out, seen = [], set()
    for item in value:
        if type(item) is not str or ID_PATTERN.fullmatch(item) is None:
            _fail(f"invalid {field}")
        if item in seen:
            _fail(f"invalid {field}")
        seen.add(item)
        out.append(item)
    return out


def _number(value: object) -> float:
    if type(value) not in (int, float) or type(value) is bool:
        _fail("invalid probability")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        _fail("invalid probability")
    return number


def _distribution(value: object, classes: list[str]) -> dict[str, float] | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != set(classes):
        _fail("invalid probability distribution")
    probs = {name: _number(value[name]) for name in classes}
    if abs(sum(probs.values()) - 1.0) > 1e-9:
        _fail("invalid probability distribution")
    return probs


def _case(value: object) -> dict:
    keys = {"case_id", "choice_ids", "target_choice_ids", "probabilities"}
    if type(value) is not dict or set(value) != keys:
        _fail("invalid probability case")
    case_id = value["case_id"]
    if type(case_id) is not str or not case_id or len(case_id) > 256:
        _fail("invalid probability case")
    choices = _ids(value["choice_ids"], "choices")
    if ABSTAIN_ID in choices:
        _fail("invalid choices")
    targets = _ids(value["target_choice_ids"], "targets", allow_empty=True)
    if any(target not in choices for target in targets):
        _fail("invalid targets")
    classes = choices + [ABSTAIN_ID]
    return {
        "case_id": case_id,
        "classes": classes,
        "targets": targets or [ABSTAIN_ID],
        "probabilities": _distribution(value["probabilities"], classes),
    }


def _prediction(probs: dict[str, float], classes: list[str]) -> tuple[str, float]:
    indexed = {name: index for index, name in enumerate(classes)}
    choice = max(classes, key=lambda name: (probs[name], -indexed[name]))
    return choice, probs[choice]


def _brier(probs: dict[str, float], classes: list[str], targets: list[str]) -> float:
    target_mass = 1.0 / len(targets)
    total = 0.0
    for name in classes:
        expected = target_mass if name in targets else 0.0
        total += (probs[name] - expected) ** 2
    return total


def _log_loss(probs: dict[str, float], targets: list[str]) -> float:
    mass = sum(probs[target] for target in targets)
    return -math.log(max(EPS, mass))


def _curve(rows: list[dict], total: int) -> list[dict]:
    out = []
    for threshold in sorted({row["confidence"] for row in rows}, reverse=True):
        covered = [row for row in rows if row["confidence"] >= threshold]
        errors = sum(1 for row in covered if not row["correct"])
        out.append({
            "threshold": threshold,
            "covered": len(covered),
            "coverage": len(covered) / total if total else None,
            "errors": errors,
            "error_rate": errors / len(covered) if covered else None,
        })
    return out


def _bins(rows: list[dict], bins: int) -> list[dict]:
    if type(bins) is not int or bins <= 0 or bins > 100:
        _fail("invalid confidence bins")
    buckets = []
    for index in range(bins):
        buckets.append({
            "bin": index,
            "lower": index / bins,
            "upper": (index + 1) / bins,
            "count": 0,
            "correct": 0,
            "mean_confidence": None,
            "accuracy": None,
        })
    sums = [0.0 for _ in buckets]
    for row in rows:
        index = min(bins - 1, int(row["confidence"] * bins))
        buckets[index]["count"] += 1
        buckets[index]["correct"] += int(row["correct"])
        sums[index] += row["confidence"]
    for index, bucket in enumerate(buckets):
        count = bucket["count"]
        if count:
            bucket["mean_confidence"] = sums[index] / count
            bucket["accuracy"] = bucket["correct"] / count
    return buckets


def evaluate_probability_cases(cases: list[dict], *, bins: int = 10) -> dict:
    """Evaluate bounded probability distributions against independent targets."""
    if type(cases) is not list or len(cases) > 100_000:
        _fail("invalid probability cases")
    seen, parsed = set(), []
    for raw in cases:
        item = _case(raw)
        if item["case_id"] in seen:
            _fail("duplicate probability case")
        seen.add(item["case_id"])
        parsed.append(item)
    scored, briers, losses = [], [], []
    for item in parsed:
        probs = item["probabilities"]
        if probs is None:
            continue
        choice, confidence = _prediction(probs, item["classes"])
        correct = choice in item["targets"]
        scored.append({
            "case_id": item["case_id"],
            "prediction": choice,
            "confidence": confidence,
            "correct": correct,
        })
        briers.append(_brier(probs, item["classes"], item["targets"]))
        losses.append(_log_loss(probs, item["targets"]))
    observed = len(scored)
    total = len(parsed)
    correct = sum(1 for row in scored if row["correct"])
    body = {
        "schema": SCHEMA,
        "input_sha256": canonical_sha256(cases),
        "counts": {
            "total": total,
            "probability_observed": observed,
            "probability_missing": total - observed,
            "correct_top1": correct,
            "wrong_top1": observed - correct,
        },
        "metrics": {
            "top1_accuracy": correct / observed if observed else None,
            "brier": sum(briers) / observed if observed else None,
            "log_loss": sum(losses) / observed if observed else None,
            "probability_coverage": observed / total if total else None,
        },
        "coverage_error_curve": _curve(scored, observed),
        "confidence_bins": _bins(scored, bins),
        "confidence_semantics": (
            "confidence is max predicted class probability from the supplied "
            "distribution; it is not evidence of calibration"),
        "does_not_prove": [
            "does not assert model calibration",
            "does not prove independent label truth or held-out provenance",
            "does not authorize execution or certify decision correctness",
        ],
    }
    return {**body, "report_sha256": canonical_sha256(body)}
