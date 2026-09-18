"""Pairwise SGD trainer for the native classifier baseline."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .classifier_features import FeatureBatchCache, candidate_feature_vector, validate_feature_buckets
from .classifier_model import LinearClassifierModel
from .decision_contract import ID_PATTERN, validate_request
from .evidence_json import canonical_sha256

TRAINING_SCHEMA = "flywheel.classifier-training-manifest/v1"
PROVENANCE_KINDS = {"synthetic", "human_reviewed", "verified_outcome", "teacher"}
EXAMPLE_KEYS = {
    "task_family", "source_group", "request",
    "acceptable_choice_ids", "label_provenance",
}
PROVENANCE_KEYS = {"kind", "source_ref"}


class ClassifierTrainingError(ValueError):
    """Training data or parameters failed closed."""


@dataclass(frozen=True)
class TrainingResult:
    model: LinearClassifierModel
    report: dict


def _id(value: object, name: str) -> str:
    if type(value) is not str or ID_PATTERN.fullmatch(value) is None:
        raise ClassifierTrainingError(f"invalid {name}")
    return value


def _source_ref(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        raise ClassifierTrainingError("invalid label provenance source")
    if any(ord(ch) < 32 for ch in value):
        raise ClassifierTrainingError("invalid label provenance source")
    return value


def _provenance(value: object) -> dict:
    if type(value) is not dict or set(value) != PROVENANCE_KEYS:
        raise ClassifierTrainingError("invalid label provenance")
    kind = value["kind"]
    if type(kind) is not str or kind not in PROVENANCE_KINDS:
        raise ClassifierTrainingError("invalid label provenance kind")
    return {"kind": kind, "source_ref": _source_ref(value["source_ref"])}


def _acceptable(value: object, eligible: set[str]) -> list[str]:
    if type(value) is not list:
        raise ClassifierTrainingError("invalid acceptable choices")
    seen, out = set(), []
    for item in value:
        cid = _id(item, "acceptable choice id")
        if cid in seen or cid not in eligible:
            raise ClassifierTrainingError("invalid acceptable choices")
        seen.add(cid)
        out.append(cid)
    return out


def validate_training_example(example: dict) -> dict:
    """Validate the frozen list-dict example shape for baseline training."""
    if type(example) is not dict or set(example) != EXAMPLE_KEYS:
        raise ClassifierTrainingError("invalid classifier training example")
    try:
        request = validate_request(example["request"])
    except ValueError as exc:
        raise ClassifierTrainingError("invalid decision request") from exc
    eligible = set(request["eligible_choice_ids"])
    acceptable = _acceptable(example["acceptable_choice_ids"], eligible)
    row = {
        "task_family": _id(example["task_family"], "task family"),
        "source_group": _id(example["source_group"], "source group"),
        "request": request,
        "acceptable_choice_ids": acceptable,
        "label_provenance": _provenance(example["label_provenance"]),
    }
    row["request_sha256"] = canonical_sha256(request)
    return row


def _manifest(rows: list[dict], *, seed: int, feature_buckets: int) -> dict:
    examples = [
        {
            "task_family": row["task_family"],
            "source_group": row["source_group"],
            "request": row["request"],
            "acceptable_choice_ids": row["acceptable_choice_ids"],
            "label_provenance": row["label_provenance"],
        }
        for row in rows
    ]
    return {
        "schema": TRAINING_SCHEMA,
        "seed": seed,
        "feature_buckets": feature_buckets,
        "examples": examples,
    }


def _sigmoid_negative(diff: float) -> float:
    if diff > 50:
        return 0.0
    if diff < -50:
        return 1.0
    return 1 / (1 + math.exp(diff))


def _dot(weights: dict[int, float], vector: dict[int, float]) -> float:
    return sum(weights.get(key, 0.0) * value for key, value in vector.items())


def _update(weights: dict[int, float], pos: dict[int, float],
            neg: dict[int, float], rate: float) -> int:
    diff = _dot(weights, pos) - _dot(weights, neg)
    step = rate * _sigmoid_negative(diff)
    if step == 0:
        return 0
    keys = set(pos) | set(neg)
    for key in keys:
        weights[key] = weights.get(key, 0.0) + step * (
            pos.get(key, 0.0) - neg.get(key, 0.0))
        if abs(weights[key]) < 1e-15:
            del weights[key]
    return 1


def train_classifier_baseline(
    examples: list[dict],
    *,
    seed: int = 0,
    epochs: int = 30,
    learning_rate: float = 0.25,
    feature_buckets: int = 512,
) -> TrainingResult:
    """Train a deterministic pairwise linear ranker from frozen examples."""
    if type(examples) is not list or not examples or len(examples) > 100_000:
        raise ClassifierTrainingError("examples must be a bounded non-empty list")
    if type(seed) is not int or type(epochs) is not int or not 1 <= epochs <= 1_000:
        raise ClassifierTrainingError("invalid training parameters")
    if type(learning_rate) not in (int, float) or not math.isfinite(learning_rate) or learning_rate <= 0:
        raise ClassifierTrainingError("invalid learning rate")
    buckets = validate_feature_buckets(feature_buckets)
    rows = [validate_training_example(item) for item in examples]
    manifest = _manifest(rows, seed=seed, feature_buckets=buckets)
    manifest_sha = canonical_sha256(manifest)
    weights_by_family: dict[str, dict[int, float]] = {}
    excluded = {"explicit_abstain_examples": 0, "no_contrast_examples": 0}
    provenance_counts: dict[str, int] = {}
    task_family_counts: dict[str, int] = {}
    updates = 0
    trainable: list[dict] = []
    for row in rows:
        family = row["task_family"]
        task_family_counts[family] = task_family_counts.get(family, 0) + 1
        kind = row["label_provenance"]["kind"]
        provenance_counts[kind] = provenance_counts.get(kind, 0) + 1
        if not row["acceptable_choice_ids"]:
            excluded["explicit_abstain_examples"] += 1
            continue
        negatives = [
            item for item in row["request"]["eligible_choice_ids"]
            if item not in set(row["acceptable_choice_ids"])
        ]
        if not negatives:
            excluded["no_contrast_examples"] += 1
            continue
        trainable.append(row)
        weights_by_family.setdefault(family, {})
    for _ in range(epochs):
        for row in trainable:
            request = row["request"]
            choices = {item["id"]: item for item in request["choices"]}
            cache = FeatureBatchCache()
            family_weights = weights_by_family[row["task_family"]]
            positives = row["acceptable_choice_ids"]
            negatives = [
                cid for cid in request["eligible_choice_ids"]
                if cid not in set(positives)
            ]
            for pos_id in positives:
                pos = candidate_feature_vector(
                    request, choices[pos_id], feature_buckets=buckets,
                    cache=cache)
                for neg_id in negatives:
                    neg = candidate_feature_vector(
                        request, choices[neg_id], feature_buckets=buckets,
                        cache=cache)
                    updates += _update(
                        family_weights, pos, neg, float(learning_rate))
    report = {
        "schema": "flywheel.classifier-training-report/v1",
        "training_manifest_sha256": manifest_sha,
        "seed": seed,
        "epochs": epochs,
        "learning_rate": float(learning_rate),
        "feature_buckets": buckets,
        "counts": {
            "total_examples": len(rows),
            "trainable_examples": len(trainable),
            "task_families": len(task_family_counts),
            "pairwise_updates": updates,
        },
        "excluded": excluded,
        "task_family_counts": dict(sorted(task_family_counts.items())),
        "label_provenance_counts": dict(sorted(provenance_counts.items())),
        "does_not_prove": [
            "training data label truth or independence",
            "generalization beyond the supplied examples",
            "calibration, automatic routing safety, or execution authorization",
        ],
    }
    model = LinearClassifierModel(
        feature_buckets=buckets,
        weights_by_family=weights_by_family,
        training_manifest_sha256=manifest_sha,
        seed=seed,
        provenance={
            "trainer": "pairwise-logistic-sgd-stdlib",
            "training_report": report,
        },
    )
    return TrainingResult(model=model, report=report)
