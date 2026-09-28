"""classifier_model.py -- a deliberately weak, uncalibrated candidate scorer.

LinearClassifierModel is a strict-JSON, stdlib-only linear model: one weight
vector per task family, scored over a bucketed feature vector. It is a BASELINE,
not a decision-maker. Its scores are raw dot products with no calibration, so
they are not probabilities and carry no threshold that means "good enough". Do
not read more into a high score than "this candidate ranked above that one".

It is fenced OUT of the automatic accept path on purpose. oracle.py states the
C2 invariant plainly: the oracle is the only thing that accepts, and no learned
model sits on the accept path. tests/test_accept_path_purity.py enforces that by
walking the verifier's import closure and asserting no model runtime is reachable
from it. A learned scorer on the accept path is exactly the preference economy
the verifier is built to refuse, and this scorer is the kind the invariant keeps
out.

So the outputs are shaped to prevent misuse as a gate. Every score envelope
records calibration.status "uncalibrated" and selection.automatic_selection_
enabled False, and proposal_from_score_envelope returns an explicit abstention
(choice_id None) rather than a pick. The DOES_NOT_PROVE constant carries the
three standing limits on every artifact and envelope: raw scores are not
probabilities; a score authorizes neither execution nor a correctness
certificate; synthetic diagnostic training does not prove generalization. The
model can rank candidates for a human or a downstream calibrated policy; it
cannot accept one.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from time import perf_counter

from .classifier_features import (
    FeatureBatchCache,
    candidate_feature_vector,
    feature_parameters,
    validate_feature_buckets,
)
from .decision_contract import validate_request
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json

ARTIFACT_SCHEMA = "flywheel.classifier-linear-baseline/v1"
SCORE_SCHEMA = "flywheel.classifier-score-envelope/v1"
MAX_ARTIFACT_BYTES = 2_000_000
MAX_FAMILIES = 128
MAX_WEIGHTS = 100_000
HEX = set("0123456789abcdef")
DOES_NOT_PROVE = [
    "raw scores are uncalibrated and are not probabilities",
    "model scores do not authorize execution or certify semantic correctness",
    "synthetic diagnostic training does not prove generalization or power",
]
ARTIFACT_KEYS = {
    "schema", "feature_parameters", "weights_by_family",
    "training_manifest_sha256", "seed", "provenance",
    "does_not_prove", "artifact_sha256",
}


class ClassifierModelError(ValueError):
    """Model artifact or scoring input failed closed."""


def _hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise ClassifierModelError("invalid model weight")
    try:
        out = float(value)
    except OverflowError as exc:
        raise ClassifierModelError("non-finite model weight") from exc
    if not math.isfinite(out):
        raise ClassifierModelError("non-finite model weight")
    return out


def _weights(value: object, buckets: int) -> dict[str, dict[int, float]]:
    if type(value) is not dict or len(value) > MAX_FAMILIES:
        raise ClassifierModelError("invalid model family weights")
    total = 0
    families: dict[str, dict[int, float]] = {}
    for family, weights in value.items():
        if type(family) is not str or not family or type(weights) is not dict:
            raise ClassifierModelError("invalid model family")
        if len(weights) + total > MAX_WEIGHTS:
            raise ClassifierModelError("model artifact has too many weights")
        total += len(weights)
        row: dict[int, float] = {}
        for key, raw_weight in weights.items():
            if type(key) is str and key.isdecimal():
                slot = int(key)
            elif type(key) is int:
                slot = key
            else:
                raise ClassifierModelError("invalid feature weight key")
            if not 0 <= slot < buckets:
                raise ClassifierModelError("feature weight key outside buckets")
            weight = _number(raw_weight)
            if weight:
                row[slot] = weight
        families[family] = row
    return families


def _artifact_sha(value: dict) -> str:
    unsigned = {key: item for key, item in value.items() if key != "artifact_sha256"}
    return canonical_sha256(unsigned)


class LinearClassifierModel:
    """Linear candidate scorer with one weight vector per task family."""

    def __init__(
        self,
        *,
        feature_buckets: int,
        weights_by_family: dict[str, dict[int, float]],
        training_manifest_sha256: str,
        seed: int,
        provenance: dict,
        artifact_sha256: str | None = None,
    ) -> None:
        self.feature_buckets = validate_feature_buckets(feature_buckets)
        if not _hex64(training_manifest_sha256):
            raise ClassifierModelError("invalid training manifest hash")
        if type(seed) is not int:
            raise ClassifierModelError("invalid seed")
        if type(provenance) is not dict:
            raise ClassifierModelError("invalid provenance")
        self.weights_by_family = _weights(weights_by_family, self.feature_buckets)
        self.training_manifest_sha256 = training_manifest_sha256
        self.seed = seed
        self.provenance = dict(provenance)
        computed = _artifact_sha(self._artifact_body())
        if artifact_sha256 is not None and artifact_sha256 != computed:
            raise ClassifierModelError("artifact checksum mismatch")
        self.artifact_sha256 = computed

    def _artifact_body(self) -> dict:
        return {
            "schema": ARTIFACT_SCHEMA,
            "feature_parameters": feature_parameters(self.feature_buckets),
            "weights_by_family": {
                family: {str(k): weights[k] for k in sorted(weights)}
                for family, weights in sorted(self.weights_by_family.items())
            },
            "training_manifest_sha256": self.training_manifest_sha256,
            "seed": self.seed,
            "provenance": self.provenance,
            "does_not_prove": list(DOES_NOT_PROVE),
        }

    def to_json_dict(self) -> dict:
        body = self._artifact_body()
        body["artifact_sha256"] = canonical_sha256(body)
        return body

    @classmethod
    def from_json_dict(cls, value: dict) -> "LinearClassifierModel":
        if type(value) is not dict or set(value) != ARTIFACT_KEYS:
            raise ClassifierModelError("invalid classifier artifact")
        if value["schema"] != ARTIFACT_SCHEMA:
            raise ClassifierModelError("invalid classifier artifact schema")
        params = value["feature_parameters"]
        if type(params) is not dict:
            raise ClassifierModelError("invalid feature parameters")
        buckets = validate_feature_buckets(params.get("feature_buckets"))
        if params != feature_parameters(buckets):
            raise ClassifierModelError("unsupported feature parameters")
        if not _hex64(value["artifact_sha256"]):
            raise ClassifierModelError("invalid artifact hash")
        return cls(
            feature_buckets=buckets,
            weights_by_family=value["weights_by_family"],
            training_manifest_sha256=value["training_manifest_sha256"],
            seed=value["seed"],
            provenance=value["provenance"],
            artifact_sha256=value["artifact_sha256"],
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "LinearClassifierModel":
        try:
            with Path(path).open("rb") as handle:
                raw = handle.read(MAX_ARTIFACT_BYTES + 1)
            value = strict_load_json(
                raw, max_bytes=MAX_ARTIFACT_BYTES, max_depth=12)
        except (OSError, ValueError, RecursionError) as exc:
            raise ClassifierModelError("invalid classifier artifact JSON") from exc
        return cls.from_json_dict(value)

    def save_json(self, path: str | Path) -> None:
        Path(path).write_bytes(canonical_bytes(self.to_json_dict()))

    def model_ref(self) -> str:
        return f"classifier-baseline:{self.artifact_sha256[:16]}"

    def _score(self, task_family: str, request: dict, choice: dict,
               cache: FeatureBatchCache) -> float:
        vector = candidate_feature_vector(
            request, choice, feature_buckets=self.feature_buckets,
            cache=cache)
        weights = self.weights_by_family.get(task_family, {})
        score = sum(weights.get(key, 0.0) * value for key, value in vector.items())
        if not math.isfinite(score):
            raise ClassifierModelError("non-finite classifier score")
        return round(score, 12)

    def predict_batch(self, requests: list[dict], *, task_family: str) -> list[dict]:
        if type(requests) is not list or len(requests) > 10_000:
            raise ClassifierModelError("requests must be a bounded list")
        if type(task_family) is not str or not task_family:
            raise ClassifierModelError("invalid task family")
        if task_family not in self.weights_by_family:
            raise ClassifierModelError("unsupported task family")
        cache = FeatureBatchCache()
        envelopes = []
        for payload in requests:
            start = perf_counter()
            try:
                request = validate_request(payload)
            except ValueError as exc:
                raise ClassifierModelError("invalid decision request") from exc
            eligible = set(request["eligible_choice_ids"])
            rows = []
            for choice in request["choices"]:
                if choice["id"] not in eligible:
                    rows.append({
                        "choice_id": choice["id"], "eligible": False,
                        "score": None, "masked_reason": "ineligible_choice",
                    })
                    continue
                rows.append({
                    "choice_id": choice["id"], "eligible": True,
                    "score": self._score(task_family, request, choice, cache),
                    "masked_reason": None,
                })
            elapsed = round((perf_counter() - start) * 1000, 3)
            envelopes.append({
                "schema": SCORE_SCHEMA,
                "model_ref": self.model_ref(),
                "artifact_sha256": self.artifact_sha256,
                "task_family": task_family,
                "request_sha256": canonical_sha256(request),
                "candidate_ids": [item["id"] for item in request["choices"]],
                "eligible_candidate_ids": list(request["eligible_choice_ids"]),
                "scores": rows,
                "scoring_latency_ms": elapsed,
                "feature_cache": cache.stats(),
                "calibration": {
                    "status": "uncalibrated",
                    "probability_semantics": "not_probabilities",
                },
                "selection": {
                    "automatic_selection_enabled": False,
                    "reason": "uncalibrated_raw_scores",
                },
                "does_not_prove": list(DOES_NOT_PROVE),
            })
        return envelopes


def proposal_from_score_envelope(envelope: dict) -> str:
    """Return an explicit abstention proposal until a calibrated policy exists."""
    if type(envelope) is not dict or envelope.get("schema") != SCORE_SCHEMA:
        raise ClassifierModelError("invalid score envelope")
    return json.dumps(
        {"choice_id": None, "evidence_refs": []},
        sort_keys=True, separators=(",", ":"))
