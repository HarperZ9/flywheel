import pytest
from solution import bucket_counts


def test_basic_half_open():
    assert bucket_counts([0, 9, 10, 20], [0, 10, 20]) == [2, 2]
    assert bucket_counts([1, 2, 3], [0, 5, 10]) == [3, 0]


def test_last_bucket_inclusive_on_right():
    assert bucket_counts([20], [0, 10, 20]) == [0, 1]
    assert bucket_counts([19, 20], [0, 10, 20]) == [0, 2]


def test_interior_edge_goes_right():
    assert bucket_counts([5], [0, 5, 10]) == [0, 1]
    assert bucket_counts([10], [0, 10, 20]) == [0, 1]
    assert bucket_counts([3, 6], [0, 3, 6, 9]) == [0, 1, 1]


def test_single_bucket_closed_both_ends():
    assert bucket_counts([0, 10, 5], [0, 10]) == [3]


def test_empty_values():
    assert bucket_counts([], [1, 2, 3]) == [0, 0]


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        bucket_counts([21], [0, 10, 20])
    with pytest.raises(ValueError):
        bucket_counts([-1], [0, 10, 20])


def test_bad_edges_raise():
    with pytest.raises(ValueError):
        bucket_counts([1], [0, 10, 10])
    with pytest.raises(ValueError):
        bucket_counts([1], [5, 3])
    with pytest.raises(ValueError):
        bucket_counts([1], [7])
    with pytest.raises(ValueError):
        bucket_counts([1], [])
    with pytest.raises(ValueError):
        bucket_counts([0], [False, 5])
    with pytest.raises(ValueError):
        bucket_counts([1], [0, 1.5, 3])


def test_bad_values_raise():
    with pytest.raises(ValueError):
        bucket_counts([True], [0, 10])
    with pytest.raises(ValueError):
        bucket_counts([1.0], [0, 10])
    with pytest.raises(ValueError):
        bucket_counts("12", [0, 10])


def test_no_mutation_of_inputs():
    values = [7, 2, 20, 2]
    edges = [0, 10, 20]
    v_snap = list(values)
    e_snap = list(edges)
    assert bucket_counts(values, edges) == [3, 1]
    assert values == v_snap
    assert edges == e_snap
