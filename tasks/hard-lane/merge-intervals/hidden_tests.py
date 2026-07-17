# HELD-OUT test suite (never shown to the model). The edge cases a shortcut misses:
# empty, single, fully-nested, UNSORTED input, and disjoint intervals.
from sol import merge_intervals


def test_empty():
    assert merge_intervals([]) == []


def test_single():
    assert merge_intervals([[1, 2]]) == [[1, 2]]


def test_fully_nested():
    assert merge_intervals([[1, 10], [2, 3]]) == [[1, 10]]


def test_unsorted_input():
    assert merge_intervals([[8, 10], [1, 3], [2, 6]]) == [[1, 6], [8, 10]]


def test_disjoint_kept_separate():
    assert merge_intervals([[1, 2], [3, 4]]) == [[1, 2], [3, 4]]
