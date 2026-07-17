import pytest
from solution import look_and_say as f
def test_zero_steps(): assert f('1', 0) == '1'
def test_one_step(): assert f('1', 1) == '11'
def test_four_steps(): assert f('1', 4) == '111221'
def test_five_steps(): assert f('1', 5) == '312211'
def test_runs(): assert f('3993', 1) == '132913'
def test_zero_digit(): assert f('0', 1) == '10'
def test_fixed_point(): assert f('22', 3) == '22'
def test_overflow():
    with pytest.raises(ValueError) as e: f('1111111111', 1)
    assert str(e.value) == 'run overflow'
def test_overflow_skipped_at_zero_steps():
    assert f('1111111111', 0) == '1111111111'
def test_bad_seed_empty():
    with pytest.raises(ValueError) as e: f('', 1)
    assert str(e.value) == 'bad seed'
def test_bad_seed_char():
    with pytest.raises(ValueError) as e: f('12a', 1)
    assert str(e.value) == 'bad seed'
def test_bad_seed_type():
    with pytest.raises(ValueError) as e: f(11, 1)
    assert str(e.value) == 'bad seed'
def test_seed_before_steps():
    with pytest.raises(ValueError) as e: f('', -1)
    assert str(e.value) == 'bad seed'
def test_bad_steps_negative():
    with pytest.raises(ValueError) as e: f('1', -1)
    assert str(e.value) == 'bad steps'
def test_bad_steps_bool():
    with pytest.raises(ValueError) as e: f('1', True)
    assert str(e.value) == 'bad steps'
