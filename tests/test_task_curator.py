"""Falsifiers for the admission gates — each gate must catch its own failure
mode, and a known-good task must clear all of them.

The load-bearing one is oracle_can_fail: a task whose hidden tests pass a
return-None stub would poison the N>=100 set with free points, and no
downstream eval could see it.
"""
import pytest

from harness.task_curator import (append_registry, curate, load_registry,
                                  screen)
from harness.tasks_lib import TaskSpec

GOOD = TaskSpec(
    "curator_add", "Implement add(a, b) returning the integer sum. Output ONLY "
    "the function definition.", "solution.py",
    "def add(a, b):\n    return a + b\n",
    "from solution import add\n"
    "def test_pos():\n    assert add(2, 3) == 5\n"
    "def test_neg():\n    assert add(-1, -1) == -2\n"
    "def test_zero():\n    assert add(0, 0) == 0\n"
    "def test_big():\n    assert add(10**9, 1) == 10**9 + 1\n",
    "hard")


def _variant(**kw):
    base = dict(task_id="curator_add", prompt=GOOD.prompt,
                candidate_filename="solution.py", solution=GOOD.solution,
                hidden_tests=GOOD.hidden_tests, difficulty="hard")
    base.update(kw)
    return TaskSpec(base.pop("task_id"), base.pop("prompt"),
                    base.pop("candidate_filename"), base.pop("solution"),
                    base.pop("hidden_tests"), base.pop("difficulty"))


def test_good_task_clears_every_gate(tmp_path):
    r = screen(GOOD, tmp_path)
    assert r["gates"] == {k: "PASS" for k in r["gates"]}, r["gates"]
    assert r["admitted"]


def test_vacuous_tests_rejected_by_oracle_can_fail(tmp_path):
    vac = _variant(task_id="vacuous", hidden_tests=(
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert 1 == 1\n"
        "def test_c():\n    assert not False\n"
        "def test_d():\n    assert []==[]\n"))
    r = screen(vac, tmp_path)
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")


def test_broken_reference_rejected(tmp_path):
    bad = _variant(task_id="broken_ref",
                   solution="def add(a, b):\n    return a - b\n")
    r = screen(bad, tmp_path)
    assert not r["admitted"]
    assert r["gates"]["reference_passes"].startswith("FAIL")


def test_solution_leaked_into_prompt_rejected(tmp_path):
    leaky = _variant(task_id="leaky",
                     prompt="Implement add. Hint: def add(a, b): return a + b")
    r = screen(leaky, tmp_path)
    assert r["gates"]["no_solution_leak"].startswith("FAIL")


def test_thin_tests_rejected_by_edge_coverage(tmp_path):
    thin = _variant(task_id="thin", hidden_tests=(
        "from solution import add\n"
        "def test_only():\n    assert add(1, 1) == 2\n"))
    r = screen(thin, tmp_path)
    assert r["gates"]["edge_coverage"].startswith("FAIL")


def test_unstubbable_solution_fails_closed(tmp_path):
    weird = _variant(task_id="unstubbable",
                     solution="add = lambda a, b: a + b\n")
    r = screen(weird, tmp_path)
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")
    assert "fail closed" in r["gates"]["oracle_can_fail"]


def test_batch_dedup_catches_twins_within_one_batch(tmp_path):
    twin = _variant(task_id="curator_add_twin")   # same solution, new id
    out = curate([GOOD, twin], tmp_path)
    assert [s.task_id for s in out["admitted"]] == ["curator_add"]
    assert "dedup" in out["rejected"]["curator_add_twin"]


def test_registry_roundtrip_and_tamper_detection(tmp_path):
    reg = tmp_path / "curated.jsonl"
    append_registry([GOOD], reg)
    (loaded,) = load_registry(reg)
    assert loaded == GOOD
    # tamper one field -> loading must refuse loudly, not eval on it
    text = reg.read_text(encoding="utf-8").replace(
        "return a + b", "return a - b")
    reg.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        load_registry(reg)
