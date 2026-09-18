import math

import pytest

torch = pytest.importorskip("torch")


class TinyBatch(dict):
    def to(self, device):
        return TinyBatch({k: v.to(device) for k, v in self.items()})


class TinyTokenizer:
    def __init__(self):
        self.vocab = {"[PAD]": 0}

    def _ids(self, text):
        ids = []
        for token in text.lower().split():
            self.vocab.setdefault(token, len(self.vocab))
            ids.append(self.vocab[token])
        return ids or [0]

    def __call__(self, texts, **_kwargs):
        rows = [self._ids(text) for text in texts]
        width = max(len(row) for row in rows)
        padded = [row + [0] * (width - len(row)) for row in rows]
        mask = [[1] * len(row) + [0] * (width - len(row)) for row in rows]
        return TinyBatch({
            "input_ids": torch.tensor(padded, dtype=torch.long),
            "attention_mask": torch.tensor(mask, dtype=torch.long),
        })


class TinyEncoder(torch.nn.Module):
    def __init__(self, hidden_size=12, vocab_size=512):
        super().__init__()
        self.config = type("Config", (), {"hidden_size": hidden_size})()
        self.emb = torch.nn.Embedding(vocab_size, hidden_size, padding_idx=0)
        with torch.no_grad():
            self.emb.weight.zero_()
            for idx in range(1, vocab_size):
                self.emb.weight[idx, idx % hidden_size] = 1.0

    def forward(self, input_ids, attention_mask=None):
        return type("Out", (), {"last_hidden_state": self.emb(input_ids)})()


def request(ref, state, choices=None, eligible=None):
    choices = choices or [
        {"id": "left", "description": "private local offline route"},
        {"id": "right", "description": "remote hosted endpoint route"},
    ]
    return {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": ref,
        "state": state,
        "choices": choices,
        "eligible_choice_ids": [c["id"] for c in choices] if eligible is None else eligible,
        "evidence_refs": ["ev"],
    }


def example(ref, state, acceptable, choices=None):
    return {
        "task_family": "routing",
        "source_group": ref,
        "request": request(ref, state, choices=choices),
        "acceptable_choice_ids": acceptable,
        "label_provenance": {"kind": "synthetic", "source_ref": f"fixture:{ref}"},
    }


def train_small(tmp_path, examples=None, *, max_length=8):
    from train.classifier_encoder import EncoderTrainConfig, train_encoder_classifier

    return train_encoder_classifier(
        examples or [
            example("local", "prefer private local offline evidence", ["left"]),
            example("remote", "prefer remote hosted endpoint", ["right"]),
            example("abstain", "insufficient evidence ask operator", []),
        ],
        tokenizer=TinyTokenizer(),
        encoder=TinyEncoder(),
        config=EncoderTrainConfig(
            seed=13,
            epochs=28,
            learning_rate=0.08,
            head_learning_rate=0.08,
            batch_size=2,
            max_length=max_length,
            device="cpu",
            fine_tune_last_n_layers=0,
        ),
    )


def distribution_by_id(envelope):
    return {row["choice_id"]: row["probability_like"] for row in envelope["scores"]}


def test_encoder_training_learns_text_features_without_candidate_id_memorization(tmp_path):
    from train.classifier_encoder_runtime import EncoderClassifierRuntime

    result = train_small(tmp_path)
    runtime = EncoderClassifierRuntime(result.model, result.tokenizer, result.report["artifact_identity"])
    heldout = request(
        "heldout",
        "route through the local private path",
        choices=[
            {"id": "beta", "description": "remote hosted endpoint route"},
            {"id": "alpha", "description": "private local offline evidence"},
        ],
    )

    envelope = runtime.score_batch([heldout], task_family="routing")[0]
    probs = distribution_by_id(envelope)

    assert probs["alpha"] > probs["beta"]
    assert envelope["calibration"]["status"] == "uncalibrated"
    assert envelope["selection"]["automatic_selection_enabled"] is False
    assert result.report["counts"]["explicit_abstain_examples"] == 1


def test_runtime_masks_ineligible_choices_and_keeps_abstain_mass(tmp_path):
    from train.classifier_encoder_runtime import EncoderClassifierRuntime

    result = train_small(tmp_path)
    runtime = EncoderClassifierRuntime(result.model, result.tokenizer, result.report["artifact_identity"])
    masked = request(
        "masked",
        "remote hosted endpoint is tempting",
        eligible=["safe"],
        choices=[
            {"id": "unsafe", "description": "remote hosted endpoint route"},
            {"id": "safe", "description": "private local offline route"},
        ],
    )

    envelope = runtime.score_batch([masked], task_family="routing")[0]
    probs = distribution_by_id(envelope)

    assert probs["unsafe"] == 0.0
    assert probs["safe"] > 0.0
    assert probs["__abstain__"] > 0.0
    assert math.isclose(sum(probs.values()), 1.0, rel_tol=1e-12)


def test_runtime_cache_is_model_bound_and_reuses_repeated_texts(tmp_path):
    from train.classifier_encoder_runtime import EncoderClassifierRuntime

    result = train_small(tmp_path)
    runtime = EncoderClassifierRuntime(
        result.model, result.tokenizer, result.report["artifact_identity"], cache_size=4)
    req = request("cache", "prefer private local offline evidence")

    first = runtime.score_batch([req], task_family="routing")[0]["encoder_cache"]
    second = runtime.score_batch([req], task_family="routing")[0]["encoder_cache"]
    runtime.set_model(result.model, "new-checkpoint")
    third = runtime.score_batch([req], task_family="routing")[0]["encoder_cache"]

    assert first["misses"] == 3
    assert second["hits"] == 3
    assert third["misses"] == 3


def test_safetensors_artifact_reload_preserves_predictions(tmp_path):
    from train.classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact
    from train.classifier_encoder_runtime import EncoderClassifierRuntime

    result = train_small(tmp_path)
    req = request("reload", "prefer remote hosted endpoint")
    before = EncoderClassifierRuntime(
        result.model, result.tokenizer, result.report["artifact_identity"]
    ).score_batch([req], task_family="routing")[0]

    save_encoder_artifact(tmp_path, result)
    loaded = load_encoder_artifact(tmp_path, tokenizer=result.tokenizer, encoder=TinyEncoder())
    after = EncoderClassifierRuntime(
        loaded.model, loaded.tokenizer, loaded.report["artifact_identity"]
    ).score_batch([req], task_family="routing")[0]

    assert distribution_by_id(before) == distribution_by_id(after)
    assert loaded.report["weights_sha256"] == result.report["weights_sha256"]


def rewrite_manifest(path, **updates):
    from harness.evidence_json import canonical_bytes, canonical_sha256, strict_load_json

    manifest_path = path / "manifest.json"
    manifest = strict_load_json(manifest_path.read_bytes())
    manifest.update(updates)
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = canonical_sha256(body)
    manifest_path.write_bytes(canonical_bytes(manifest))
    return manifest


def test_artifact_loader_rejects_traversal_even_with_recomputed_manifest_hash(tmp_path):
    from train.classifier_encoder import EncoderClassifierError
    from train.classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact

    result = train_small(tmp_path)
    save_encoder_artifact(tmp_path, result)
    rewrite_manifest(tmp_path, weights_path="../model.safetensors")

    with pytest.raises(EncoderClassifierError, match="manifest"):
        load_encoder_artifact(tmp_path, tokenizer=result.tokenizer, encoder=TinyEncoder())


def test_artifact_loader_rejects_conflicting_report_identity(tmp_path):
    from harness.evidence_json import canonical_bytes, strict_load_json
    from train.classifier_encoder import EncoderClassifierError
    from train.classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact

    result = train_small(tmp_path)
    save_encoder_artifact(tmp_path, result)
    report_path = tmp_path / "train_report.json"
    report = strict_load_json(report_path.read_bytes())
    report["artifact_identity"] = "classifier-encoder:forged"
    report_path.write_bytes(canonical_bytes(report))
    rewrite_manifest(tmp_path, training_report_sha256=__import__("hashlib").sha256(
        canonical_bytes(report)).hexdigest())

    with pytest.raises(EncoderClassifierError, match="report"):
        load_encoder_artifact(tmp_path, tokenizer=result.tokenizer, encoder=TinyEncoder())


def test_artifact_loader_rejects_mutated_bundled_tokenizer_file(tmp_path):
    from train.classifier_encoder import EncoderClassifierError
    from train.classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact

    model_dir = tmp_path / "base"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"model_type":"tiny"}', encoding="utf-8")
    (model_dir / "tokenizer_config.json").write_text('{"tokenizer_class":"Tiny"}', encoding="utf-8")
    artifact = tmp_path / "artifact"
    result = train_small(tmp_path)
    save_encoder_artifact(artifact, result, pretrained_model_path=str(model_dir))
    (artifact / "tokenizer" / "tokenizer_config.json").write_text('{"tampered":true}', encoding="utf-8")

    with pytest.raises(EncoderClassifierError, match="resource"):
        load_encoder_artifact(artifact, tokenizer=result.tokenizer, encoder=TinyEncoder())


def test_artifact_save_refuses_overwrite_and_manifest_bounded_read(tmp_path):
    from train.classifier_encoder import EncoderClassifierError
    from train.classifier_encoder_artifact import load_encoder_artifact, save_encoder_artifact

    result = train_small(tmp_path)
    save_encoder_artifact(tmp_path, result)
    with pytest.raises(EncoderClassifierError, match="fresh"):
        save_encoder_artifact(tmp_path, result)

    big = tmp_path / "big"
    big.mkdir()
    (big / "manifest.json").write_bytes(b" " * 200_000)
    with pytest.raises(EncoderClassifierError, match="manifest"):
        load_encoder_artifact(big, tokenizer=result.tokenizer, encoder=TinyEncoder())


def test_long_inputs_are_rejected_without_truncation(tmp_path):
    from train.classifier_encoder import EncoderClassifierError
    from train.classifier_encoder_runtime import EncoderClassifierRuntime

    result = train_small(tmp_path)
    runtime = EncoderClassifierRuntime(result.model, result.tokenizer, result.report["artifact_identity"])

    with pytest.raises(EncoderClassifierError, match="sequence length"):
        runtime.score_batch([
            request("long", "one two three four five six seven eight nine")
        ], task_family="routing")
