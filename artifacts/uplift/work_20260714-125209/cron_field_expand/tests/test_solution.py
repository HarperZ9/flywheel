import pytest
from solution import cron_field as f
def test_star(): assert f('*', 0, 5) == [0, 1, 2, 3, 4, 5]
def test_star_step(): assert f('*/15', 0, 59) == [0, 15, 30, 45]
def test_range_step(): assert f('3-7/2', 0, 59) == [3, 5, 7]
def test_list_dedup(): assert f('1,5,3,5', 0, 59) == [1, 3, 5]
def test_mixed(): assert f('10-12,1', 0, 59) == [1, 10, 11, 12]
def test_leading_zero_value(): assert f('05', 0, 59) == [5]
def test_step_on_value():
    with pytest.raises(ValueError) as e: f('5/2', 0, 59)
    assert str(e.value) == 'bad field'
def test_reversed_range():
    with pytest.raises(ValueError) as e: f('7-3', 0, 59)
    assert str(e.value) == 'bad range'
def test_out_of_range():
    with pytest.raises(ValueError) as e: f('0-99', 0, 59)
    assert str(e.value) == 'out of range'
def test_zero_step():
    with pytest.raises(ValueError) as e: f('*/0', 0, 59)
    assert str(e.value) == 'bad step'
def test_bad_bounds():
    with pytest.raises(ValueError) as e: f('*', 5, 0)
    assert str(e.value) == 'bad bounds'
def test_empty_field():
    with pytest.raises(ValueError) as e: f('', 0, 5)
    assert str(e.value) == 'bad field'
