import json

import pytest

pytest.importorskip("torch")


def request(ref, state):
    return {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": ref,
        "state": state,
        "choices": [
            {"id": "local", "description": "local private path"},
            {"id": "remote", "description": "remote hosted path"},
        ],
        "eligible_choice_ids": ["local", "remote"],
        "evidence_refs": ["ev"],
    }


def example(group, ref, state, acceptable):
    return {
        "task_family": "routing",
        "source_group": group,
        "request": request(ref, state),
        "acceptable_choice_ids": acceptable,
        "label_provenance": {"kind": "synthetic", "source_ref": f"fixture:{ref}"},
    }


def test_cli_training_loader_strips_enriched_rows_and_filters_train_split(tmp_path):
    from harness.classifier_dataset import build_split_manifest
    from harness.evidence_json import canonical_bytes
    from train.classifier_encoder_cli import _load_training_examples

    rows = [
        example("g-train", "train", "prefer local", ["local"]),
        example("g-test", "test", "prefer remote", ["remote"]),
    ]
    examples_path = tmp_path / "examples.jsonl"
    examples_path.write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )
    manifest = build_split_manifest(rows, {"g-train": "train", "g-test": "test"})
    manifest_path = tmp_path / "splits.json"
    manifest_path.write_bytes(canonical_bytes(manifest))

    loaded = _load_training_examples(examples_path, manifest_path)

    assert loaded == [rows[0]]
    assert set(loaded[0]) == {
        "task_family", "source_group", "request",
        "acceptable_choice_ids", "label_provenance",
    }


def test_cli_split_manifest_must_cover_examples_and_match_manifest_hash(tmp_path):
    from harness.classifier_dataset import build_split_manifest
    from harness.evidence_json import canonical_bytes
    from train.classifier_encoder_cli import _load_training_examples

    rows = [
        example("g-train", "train", "prefer local", ["local"]),
        example("g-test", "test", "prefer remote", ["remote"]),
    ]
    examples_path = tmp_path / "examples.jsonl"
    examples_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    manifest = build_split_manifest(rows, {"g-train": "train", "g-test": "test"})
    manifest["examples"] = manifest["examples"][:1]
    manifest_path = tmp_path / "splits.json"
    manifest_path.write_bytes(canonical_bytes(manifest))

    with pytest.raises(SystemExit, match="split manifest"):
        _load_training_examples(examples_path, manifest_path)
