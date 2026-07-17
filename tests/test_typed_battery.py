"""Falsifier for the type-aware consensus battery.

The old mixed-type battery generated wrong-typed inputs (ints where lists
were expected), causing all candidates to crash identically and erasing
behavioral signal. The type-aware battery infers parameter types and draws
from typed pools. These tests verify the fix works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_ablation import (
    _infer_param_types, _battery, _signature, consensus_select,
    _INT_POOL, _LIST_INT_POOL, _STR_POOL, _MATRIX_POOL,
)


def test_infer_list_int_params():
    types = _infer_param_types("def sliding_window_max(nums, k):\n    pass\n")
    assert types == ["list_int", "int"], f"got {types}"


def test_infer_str_params():
    types = _infer_param_types("def header_unfold(s):\n    pass\n")
    assert types == ["str"], f"got {types}"


def test_infer_matrix_params():
    types = _infer_param_types("def transpose(m):\n    pass\n")
    assert types == ["matrix"], f"got {types}"


def test_infer_multi_int_params():
    types = _infer_param_types("def splice(items, start, stop, replacement):\n    pass\n")
    assert types == ["list_int", "int", "int", "list_int"], f"got {types}"


def test_infer_annotated():
    code = "def foo(x: int, y: list[str]) -> str:\n    pass\n"
    types = _infer_param_types(code)
    assert types == ["int", "list_str"], f"got {types}"


def test_battery_typed_all_lists():
    bat = _battery(2, n=6, param_types=["list_int", "int"])
    for row in bat:
        assert isinstance(row[0], list), f"param 0 should be list, got {type(row[0])}"
        assert isinstance(row[1], int), f"param 1 should be int, got {type(row[1])}"


def test_battery_typed_matrix():
    bat = _battery(1, n=6, param_types=["matrix"])
    for row in bat:
        assert isinstance(row[0], list), f"param 0 should be list, got {type(row[0])}"


def test_battery_offset_different_values():
    """Same-type params at different positions get different values."""
    bat = _battery(4, n=8, param_types=["int", "int", "int", "int"])
    distinct_count = 0
    for row in bat:
        if len(set(row)) > 1:
            distinct_count += 1
    assert distinct_count >= 4, f"only {distinct_count}/8 rows have distinct values"


def test_battery_mixed_fallback():
    bat = _battery(2, n=6, param_types=None)
    assert len(bat) == 6
    for row in bat:
        assert len(row) == 2


def test_consensus_select_typed_distinguishes(tmp_path):
    """Two correct + two wrong candidates: typed battery should cluster correctly."""
    correct = "def add(nums, k):\n    return sum(nums[:k])\n"
    wrong1 = "def add(nums, k):\n    return len(nums)\n"
    wrong2 = "def add(nums, k):\n    return k\n"
    cands = [wrong1, correct, wrong2, correct]
    idx, conf = consensus_select(cands, "add", 2, tmp_path,
                                param_types=["list_int", "int"])
    selected = cands[idx]
    assert selected == correct, f"selected candidate[{idx}], expected a correct one"
    assert conf >= 0.5, f"confidence should be >= 0.5 with 2 correct, got {conf}"
