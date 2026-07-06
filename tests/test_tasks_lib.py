"""tasks_lib falsifier — benchmark integrity.

Every held-out task's reference solution must pass its own hidden tests (else
the benchmark is broken — an unsatisfiable task measures nothing). A wrong
solution must fail (the oracle discriminates). Materialization must produce the
format harness/task.py loads.
"""
import shutil
from pathlib import Path

import pytest

from harness.tasks_lib import (REGISTRY, materialize, materialize_all,
                               validate_spec, validate_registry)
from harness.task import load_task

WRONG = "def add(a, b):\n    return a * b\n"


def test_every_task_reference_solution_passes_its_hidden_tests(tmp_path):
    """Benchmark integrity: no task in the registry is unsatisfiable."""
    results = validate_registry(REGISTRY, tmp_path)
    broken = [tid for tid, ok in results.items() if not ok]
    assert not broken, f"reference solutions fail their own hidden tests: {broken}"


@pytest.mark.parametrize("spec", REGISTRY, ids=[s.task_id for s in REGISTRY])
def test_each_task_reference_passes(spec, tmp_path):
    assert validate_spec(spec, tmp_path / "v"), (
        f"{spec.task_id}: reference solution must pass hidden tests")


@pytest.mark.parametrize("spec", REGISTRY, ids=[s.task_id for s in REGISTRY])
def test_wrong_solution_fails(spec, tmp_path):
    """The oracle must discriminate — a wrong solution fails the hidden tests."""
    from harness.oracle import PytestOracle
    work = tmp_path / spec.task_id
    materialize(spec, work)
    task = load_task(work)
    orc = PytestOracle()
    r = orc.verify("pass\n", task)  # the 'pass' stub never satisfies real tests
    assert not r.passed, f"{spec.task_id}: oracle must reject a no-op solution"


def test_materialize_all_creates_loadable_tasks(tmp_path):
    dirs = materialize_all(REGISTRY, tmp_path / "set")
    assert len(dirs) == len(REGISTRY)
    for spec, d in zip(REGISTRY, dirs):
        task = load_task(d)
        assert task.task_id == spec.task_id
        assert task.candidate_path == spec.candidate_filename


def test_registry_has_difficulty_spread():
    diffs = {s.difficulty for s in REGISTRY}
    assert "easy" in diffs and "medium" in diffs and "hard" in diffs
    assert len(REGISTRY) >= 6, "need enough tasks for a meaningful pass rate"


def test_registry_tasks_have_edge_case_tests():
    """Hidden tests must include edge cases (empty/None/negatives) so the oracle
    catches plausible-but-fragile solutions, not just the happy path."""
    for spec in REGISTRY:
        t = spec.hidden_tests.lower()
        assert any(k in t for k in ("empty", "none", "neg", "tie", "dup", "zero", "one")), (
            f"{spec.task_id}: hidden tests lack edge cases")
