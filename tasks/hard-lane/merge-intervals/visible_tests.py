# visible test suite (shown to the model). Named so it is not auto-collected by
# `pytest`; the oracle runs it explicitly.
from sol import merge_intervals


def test_basic_overlap():
    assert merge_intervals([[1, 3], [2, 6], [8, 10]]) == [[1, 6], [8, 10]]


def test_touching_merges():
    assert merge_intervals([[1, 4], [4, 5]]) == [[1, 5]]
