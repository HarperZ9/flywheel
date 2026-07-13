"""curator falsifier for the hard benchmark — every reference must pass.

A held-out task whose reference solution fails its own hidden tests is a broken
benchmark. This validates all HARD_REGISTRY references (and, in doing so, verifies
my reference implementations are correct before the model is judged against them).
"""
import pytest

from harness.tasks_hard import HARD_REGISTRY
from harness.tasks_lib import materialize_all
from harness.task import load_task
from harness.oracle import PytestOracle


@pytest.mark.parametrize("spec", HARD_REGISTRY, ids=lambda s: s.task_id)
def test_reference_solution_passes_its_own_tests(spec, tmp_path):
    d = materialize_all([spec], tmp_path / "t")[0]
    task = load_task(d)
    r = PytestOracle().verify(spec.solution, task)
    assert r.passed, f"{spec.task_id}: reference FAILS its own hidden tests (broken benchmark)"


def test_hard_set_is_hard_and_sized():
    assert len(HARD_REGISTRY) >= 8
    assert all(s.difficulty == "hard" for s in HARD_REGISTRY)
    assert len({s.task_id for s in HARD_REGISTRY}) == len(HARD_REGISTRY)  # unique ids


def test_a_naive_wrong_solution_is_rejected(tmp_path):
    # sanity: the hidden tests actually discriminate — a wrong solution must fail.
    spec = next(s for s in HARD_REGISTRY if s.task_id == "roman_to_int")
    d = materialize_all([spec], tmp_path / "t")[0]
    task = load_task(d)
    wrong = "def roman_to_int(s):\n    return len(s)\n"   # ignores values
    assert PytestOracle().verify(wrong, task).passed is False
