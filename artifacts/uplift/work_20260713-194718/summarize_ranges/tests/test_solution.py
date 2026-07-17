import pytest
from solution import summarize_ranges as f
def test_basic(): assert f([0, 1, 2, 4, 5, 7]) == ['0->2', '4->5', '7']
def test_empty(): assert f([]) == []
def test_single(): assert f([1]) == ['1']
def test_all_isolated(): assert f([1, 3, 5]) == ['1', '3', '5']
def test_negatives(): assert f([-3, -2, -1, 2]) == ['-3->-1', '2']
def test_one_run(): assert f([1, 2, 3, 4]) == ['1->4']
def test_not_sorted():
    with pytest.raises(ValueError) as e: f([3, 1])
    assert str(e.value) == 'not sorted'
def test_duplicate():
    with pytest.raises(ValueError) as e: f([1, 1])
    assert str(e.value) == 'not sorted'
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1, True])
    assert str(e.value) == 'bad item'
