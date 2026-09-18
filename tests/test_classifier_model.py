import math
from pathlib import Path

import pytest

from harness.decision_contract import evaluate_proposal


def request(ref, state, *, eligible=None, choices=None):
    route_choices = choices or [
        {"id": "left", "description": "offline private local evidence route"},
        {"id": "right", "description": "hosted remote endpoint route"},
    ]
    return {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": ref,
        "state": state,
        "choices": route_choices,
        "eligible_choice_ids": [item["id"] for item in route_choices] if eligible is None else eligible,
        "evidence_refs": ["ev_route"],
    }


def example(group, ref, state, acceptable, *, family="routing", choices=None):
    return {
        "task_family": family,
        "source_group": group,
        "request": request(ref, state, choices=choices),
        "acceptable_choice_ids": acceptable,
        "label_provenance": {
            "kind": "verified_outcome",
            "source_ref": f"receipt:{ref}",
        },
    }


def training_rows():
    return [
        example("session-local", "local-1", "Need offline private local evidence.", ["left"]),
        example("session-hosted", "hosted-1", "Need hosted remote endpoint.", ["right"]),
        example("session-abstain", "defer-1", "The route was explicitly deferred.", []),
    ]


def score_by_id(envelope):
    return {row["choice_id"]: row for row in envelope["scores"]}


def test_training_learns_description_features_and_serializes_without_candidate_id_memorization(tmp_path):
    from harness.classifier_model import LinearClassifierModel
    from harness.classifier_training import train_classifier_baseline

    result = train_classifier_baseline(
        training_rows(), seed=7, epochs=60, learning_rate=0.4, feature_buckets=128)

    assert result.report["excluded"]["explicit_abstain_examples"] == 1
    held_out = [
        request(
            "local-heldout",
            "Choose the private offline route.",
            choices=[
                {"id": "alpha", "description": "private local evidence workflow"},
                {"id": "beta", "description": "remote hosted endpoint workflow"},
            ],
        ),
        request(
            "hosted-heldout",
            "Choose the remote hosted endpoint.",
            choices=[
                {"id": "alpha", "description": "private local evidence workflow"},
                {"id": "beta", "description": "remote hosted endpoint workflow"},
            ],
        ),
    ]

    first, second = result.model.predict_batch(held_out, task_family="routing")
    assert score_by_id(first)["alpha"]["score"] > score_by_id(first)["beta"]["score"]
    assert score_by_id(second)["beta"]["score"] > score_by_id(second)["alpha"]["score"]
    assert first["calibration"]["status"] == "uncalibrated"
    assert first["selection"]["automatic_selection_enabled"] is False

    artifact = tmp_path / "classifier.json"
    result.model.save_json(artifact)
    loaded = LinearClassifierModel.load_json(artifact)
    loaded_first, loaded_second = loaded.predict_batch(held_out, task_family="routing")

    assert [row["score"] for row in first["scores"]] == [
        row["score"] for row in loaded_first["scores"]]
    assert [row["score"] for row in second["scores"]] == [
        row["score"] for row in loaded_second["scores"]]
    assert loaded.artifact_sha256 == result.model.artifact_sha256
    assert loaded.to_json_dict()["training_manifest_sha256"] == result.report["training_manifest_sha256"]


def test_predict_batch_masks_ineligible_candidates_and_reuses_state_features():
    from harness.classifier_training import train_classifier_baseline

    model = train_classifier_baseline(
        training_rows(), seed=3, epochs=40, learning_rate=0.35, feature_buckets=96).model
    repeated = request(
        "mask-1",
        "Need hosted remote endpoint.",
        eligible=["safe"],
        choices=[
            {"id": "unsafe", "description": "hosted remote endpoint route"},
            {"id": "safe", "description": "offline private local evidence route"},
        ],
    )

    first, second = model.predict_batch([repeated, repeated], task_family="routing")

    assert score_by_id(first)["unsafe"] == {
        "choice_id": "unsafe",
        "eligible": False,
        "score": None,
        "masked_reason": "ineligible_choice",
    }
    assert math.isfinite(score_by_id(first)["safe"]["score"])
    assert first["feature_cache"]["state_cache_hits"] == 0
    assert second["feature_cache"]["state_cache_hits"] == 1


def test_uncalibrated_envelope_does_not_auto_select_and_contract_accepts_abstain():
    from harness.classifier_model import proposal_from_score_envelope
    from harness.classifier_training import train_classifier_baseline

    req = request("proposal-1", "Need offline private local evidence.")
    model = train_classifier_baseline(
        training_rows(), seed=5, epochs=40, learning_rate=0.35, feature_buckets=96).model
    envelope = model.predict_batch([req], task_family="routing")[0]

    response = proposal_from_score_envelope(envelope)
    result = evaluate_proposal(req, response, scorer_ref="classifier-baseline")

    assert envelope["selection"]["reason"] == "uncalibrated_raw_scores"
    assert result["reason_code"] == "abstain"
    assert result["choice_id"] is None


def test_training_reuses_decision_request_validation():
    from harness.classifier_training import ClassifierTrainingError, train_classifier_baseline

    bad = training_rows()
    bad[0] = {**bad[0], "request": {**bad[0]["request"], "state": ""}}

    with pytest.raises(ClassifierTrainingError):
        train_classifier_baseline(bad)


def test_artifact_loader_rejects_tampering_and_nonfinite_weights():
    from harness.classifier_model import ClassifierModelError, LinearClassifierModel
    from harness.classifier_training import train_classifier_baseline

    model = train_classifier_baseline(
        training_rows(), seed=11, epochs=20, learning_rate=0.25, feature_buckets=64).model
    artifact = model.to_json_dict()
    tampered = dict(artifact, training_manifest_sha256="0" * 64)

    with pytest.raises(ClassifierModelError):
        LinearClassifierModel.from_json_dict(tampered)

    unsigned = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    unsigned["weights_by_family"] = {"routing": {"1": float("nan")}}
    unsigned["artifact_sha256"] = artifact["artifact_sha256"]
    with pytest.raises(ClassifierModelError):
        LinearClassifierModel.from_json_dict(unsigned)


def test_load_json_reads_only_bounded_prefix_before_rejecting_oversize(tmp_path, monkeypatch):
    from harness import classifier_model
    from harness.classifier_model import ClassifierModelError, LinearClassifierModel

    path = tmp_path / "oversize.json"
    path.write_bytes(b'{"schema":"' + (b"x" * classifier_model.MAX_ARTIFACT_BYTES) + b'"}')
    observed_reads = []
    real_open = Path.open

    class Reader:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def read(self, size=-1):
            observed_reads.append(size)
            return self.wrapped.read(size)

    def bounded_open(self, *args, **kwargs):
        return Reader(real_open(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", bounded_open)

    with pytest.raises(ClassifierModelError):
        LinearClassifierModel.load_json(path)

    assert observed_reads == [classifier_model.MAX_ARTIFACT_BYTES + 1]


def test_predict_batch_rejects_unsupported_task_family():
    from harness.classifier_model import ClassifierModelError
    from harness.classifier_training import train_classifier_baseline

    model = train_classifier_baseline(training_rows()).model

    with pytest.raises(ClassifierModelError, match="unsupported task family"):
        model.predict_batch([request("unsupported-1", "Need offline route.")], task_family="tool")


def test_huge_numeric_weight_rejects_as_model_value_error_not_overflow():
    from harness.classifier_model import ClassifierModelError, LinearClassifierModel
    from harness.classifier_training import train_classifier_baseline

    artifact = train_classifier_baseline(training_rows()).model.to_json_dict()
    artifact["weights_by_family"] = {"routing": {"1": 10 ** 5000}}

    with pytest.raises(ClassifierModelError):
        LinearClassifierModel.from_json_dict(artifact)
