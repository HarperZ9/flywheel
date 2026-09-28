import json

import pytest

from harness.classifier_cli import main
from tests.test_classifier_model import training_rows


def test_cli_trains_only_train_groups_then_scores_without_selecting(tmp_path, capsys):
    rows = training_rows()
    data = tmp_path / "data.jsonl"
    data.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf8")
    splits = tmp_path / "splits.json"
    splits.write_text(json.dumps({r["source_group"]: "train" for r in rows}))
    out = tmp_path / "model"
    assert main(["train", "--data", str(data), "--splits", str(splits),
                 "--out", str(out), "--epochs", "2"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["training_examples"] == 3
    assert (out / "model.json").exists()
    requests = tmp_path / "requests.json"
    requests.write_text(json.dumps([rows[0]["request"]]))
    scores = tmp_path / "scores.json"
    assert main(["score", "--model", str(out / "model.json"), "--family", "routing",
                 "--requests", str(requests), "--out", str(scores)]) == 0
    result = json.loads(scores.read_text())
    assert result[0]["selection"]["automatic_selection_enabled"] is False
    assert result[0]["task_family"] == "routing"


def test_no_training_examples_fails_without_writing_model(tmp_path):
    row = training_rows()[0]
    data = tmp_path / "data.jsonl"
    data.write_text(json.dumps(row))
    splits = tmp_path / "splits.json"
    splits.write_text(json.dumps({row["source_group"]: "test"}))
    out = tmp_path / "model"
    with pytest.raises(ValueError, match="training"):
        main(["train", "--data", str(data), "--splits", str(splits), "--out", str(out)])
    assert not out.exists()
