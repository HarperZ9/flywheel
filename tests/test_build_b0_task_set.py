import json
from pathlib import Path

import pytest

from harness.verified_bench import load_task_set
from scripts.build_b0_task_set import build

CURATED = Path(__file__).resolve().parents[1] / "tasks" / "curated" / "hard_v3.jsonl"


def test_build_produces_strict_loadable_set(tmp_path):
    n = build(CURATED, tmp_path, limit=3)
    assert n == 3
    rows = load_task_set(tmp_path / "task_set.jsonl")
    assert len(rows) == 3
    for row in rows:
        assert set(row) >= {"task_id", "prompt", "gate_cmd"}
        assert row["gate_cmd"] == f"python -m harness.b0_gate {row['task_id']}"


def test_each_task_has_a_hidden_fixture(tmp_path):
    build(CURATED, tmp_path, limit=3)
    for row in load_task_set(tmp_path / "task_set.jsonl"):
        hidden = tmp_path / row["task_id"] / "hidden_test.py"
        assert hidden.exists()
        assert "def test_" in hidden.read_text(encoding="utf-8")


def test_prompt_does_not_leak_the_hidden_test(tmp_path):
    build(CURATED, tmp_path, limit=3)
    for row in load_task_set(tmp_path / "task_set.jsonl"):
        assert "def test_" not in row["prompt"]


def test_rejects_duplicate_curated_rows(tmp_path):
    rows = CURATED.read_text(encoding="utf-8").splitlines()
    source = tmp_path / "duplicate.jsonl"
    source.write_text(rows[0] + "\n" + rows[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task id"):
        build(source, tmp_path / "out")
