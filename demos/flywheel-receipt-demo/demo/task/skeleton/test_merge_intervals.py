# The oracle. A third party re-runs exactly this file against the candidate
# answer to decide the verdict. Nothing in the demo can accept an answer these
# tests reject.
from solution import merge_intervals


def test_overlapping():
    assert merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]


def test_touching_merge():
    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]


def test_unsorted_input():
    assert merge_intervals([[15, 18], [1, 3], [8, 10], [2, 6]]) == [[1, 6], [8, 10], [15, 18]]


def test_nested():
    assert merge_intervals([[1, 10], [2, 3], [4, 5]]) == [[1, 10]]


def test_empty():
    assert merge_intervals([]) == []


def test_single():
    assert merge_intervals([[5, 7]]) == [[5, 7]]
