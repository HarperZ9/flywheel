"""Falsifiers for the data-flywheel measurement (the Stargate-for-Data counter).

Load-bearing: (1) criterion conservation computes an honest token split (the
ratio is real, not asserted, and does not overclaim); (2) manufactured yield
counts witnessed gradable triples AND always carries the amortization ceiling,
so no 'infinite data' reading can survive.
"""
from harness.data_flywheel import (
    criterion_conservation,
    estimate_tokens,
    manufactured_yield,
)


def _spec(task_id, prompt, solution, tests):
    return {"task_id": task_id, "prompt": prompt, "solution": solution,
            "hidden_tests": tests}


SPECS = [
    _spec("add", "Implement add(a,b) returning the sum. Output ONLY the function.",
          "def add(a, b):\n    return a + b\n",
          "from solution import add\ndef test():\n    assert add(2,3)==5\n"),
    _spec("mul", "Implement mul(a,b) returning the product. Output ONLY the function.",
          "def mul(a, b):\n    return a * b\n",
          "from solution import mul\ndef test():\n    assert mul(2,3)==6\n"),
]


def test_criterion_conservation_split_is_consistent():
    cc = criterion_conservation(SPECS)
    assert cc["tasks"] == 2
    # the parts sum to the whole
    assert cc["criterion_tokens"] + cc["solution_tokens"] < cc["artifact_tokens"]
    assert cc["kept_if_regenerating_solutions"] == cc["artifact_tokens"] - cc["solution_tokens"]
    # the conservation ratio equals artifact / kept, >= 1.0 (never a saving > total)
    assert cc["conservation_ratio"] == round(
        cc["artifact_tokens"] / cc["kept_if_regenerating_solutions"], 3)
    assert cc["conservation_ratio"] >= 1.0
    assert 0.0 <= cc["solution_share"] <= 1.0


def test_conservation_does_not_overclaim():
    # the saving cannot exceed the solution share — no fabricated efficiency
    cc = criterion_conservation(SPECS)
    saving = 1.0 - cc["kept_if_regenerating_solutions"] / cc["artifact_tokens"]
    assert abs(saving - cc["solution_share"]) < 1e-4   # solution_share is 4-dp rounded


def test_manufactured_yield_counts_witnessed_triples_and_carries_the_ceiling():
    my = manufactured_yield(SPECS)
    assert my["gradable_triples"] == 2
    assert my["witnessed"] is True
    assert my["oracle_calls"] == 2
    # the honest ceiling MUST be present — no unbounded-data reading survives
    assert "1/(1-r)" in my["amortization_ceiling"]
    assert "NO compounding" in my["amortization_ceiling"]


def test_deterministic():
    assert criterion_conservation(SPECS) == criterion_conservation(SPECS)
    assert estimate_tokens("a, b.") == 4


def test_reads_real_taskspecs_and_dict_rows():
    # both a dict row and an object with .prompt/.solution/.hidden_tests work
    from harness.tasks_lib import REGISTRY
    cc = criterion_conservation(list(REGISTRY)[:3])
    assert cc["tasks"] == 3 and cc["artifact_tokens"] > 0
