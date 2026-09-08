"""Operator-selected benchmark paths cannot redirect materialization."""
from dataclasses import replace
from pathlib import Path

import pytest

from harness.tasks_hard import HARD_REGISTRY
from scripts.run_uplift_live import prepare


@pytest.mark.parametrize("field,value", [
    (field, value)
    for field in ("task_id", "candidate_filename")
    for value in ("../escape", "..\\escape", "/escape", "C:\\escape",
                  "C:escape", "a/b", "a\\b", "CON", "nul.py", "x.", "x ")
])
def test_invalid_names_rejected_before_any_materialization(tmp_path, monkeypatch, field, value):
    work = tmp_path / "work"
    specs = [HARD_REGISTRY[0], replace(HARD_REGISTRY[1], **{field: value})]
    # Never let an intentionally absolute invalid input touch a real root.
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: pytest.fail("write before validation"))
    with pytest.raises(ValueError):
        prepare(work, specs)
    assert list(tmp_path.iterdir()) == []


def test_case_colliding_task_ids_rejected_before_materialization(tmp_path):
    first = replace(HARD_REGISTRY[0], task_id="Task")
    second = replace(HARD_REGISTRY[1], task_id="task")
    with pytest.raises(ValueError):
        prepare(tmp_path / "work", [first, second])
    assert list(tmp_path.iterdir()) == []


def test_existing_run_directory_is_preserved(tmp_path):
    work = tmp_path / "work"
    target = work / HARD_REGISTRY[0].task_id / "tests" / "test_solution.py"
    target.parent.mkdir(parents=True)
    target.write_text("operator-owned", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare(work, [HARD_REGISTRY[0]])
    assert target.read_text(encoding="utf-8") == "operator-owned"


def test_lane_cannot_redirect_output(tmp_path):
    with pytest.raises(ValueError):
        prepare(tmp_path / "work", [HARD_REGISTRY[0]], lane="../escape")
    assert list(tmp_path.iterdir()) == []


def test_candidate_cannot_replace_tests_directory(tmp_path):
    with pytest.raises(ValueError):
        prepare(tmp_path / "work", [replace(HARD_REGISTRY[0], candidate_filename="tests")])
    assert list(tmp_path.iterdir()) == []
