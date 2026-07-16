import pytest
from solution import apportion


def test_exact_no_remainder():
    assert apportion([2, 3, 5], 10) == [2, 3, 5]
    assert apportion([7, 13, 29, 51], 100) == [7, 13, 29, 51]


def test_tie_broken_by_lowest_index():
    assert apportion([1, 1, 1], 100) == [34, 33, 33]
    assert apportion([1, 1, 1, 1], 6) == [2, 2, 1, 1]


def test_largest_remainder_wins():
    assert apportion([500, 499, 1], 10) == [5, 5, 0]
    assert apportion([7, 13, 29], 1000) == [143, 265, 592]


def test_zero_weight_never_gets_extra():
    assert apportion([0, 5], 7) == [0, 7]
    assert apportion([0, 1, 1], 5) == [0, 3, 2]


def test_total_zero():
    assert apportion([3, 2], 0) == [0, 0]


def test_sum_invariant_and_length():
    out = apportion([3, 1, 4, 1, 5, 9, 2, 6], 1234)
    assert sum(out) == 1234
    assert len(out) == 8


def test_no_mutation():
    w = [5, 3, 2]
    snapshot = list(w)
    apportion(w, 7)
    assert w == snapshot


def test_error_contracts():
    with pytest.raises(ValueError):
        apportion([], 10)
    with pytest.raises(ValueError):
        apportion([-1, 2], 10)
    with pytest.raises(ValueError):
        apportion([0, 0], 10)
    with pytest.raises(ValueError):
        apportion([1, 2], -1)
    with pytest.raises(ValueError):
        apportion([True, 1], 10)
    with pytest.raises(ValueError):
        apportion([1, 2], True)
    with pytest.raises(ValueError):
        apportion([1.5, 2], 10)
