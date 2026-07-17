import pytest
from solution import fletcher16 as f
def test_abcde(): assert f('abcde') == 51440
def test_abcdef(): assert f('abcdef') == 8279
def test_empty_str(): assert f('') == 0
def test_empty_list(): assert f([]) == 0
def test_single(): assert f([1]) == 257
def test_two(): assert f([1, 2]) == 1027
def test_byte_255(): assert f([255]) == 0
def test_two_255(): assert f([255, 255]) == 0
def test_str_list_agree(): assert f('abcde') == f([97, 98, 99, 100, 101])
def test_bad_char():
    with pytest.raises(ValueError) as e: f('caf\xe9')
    assert str(e.value) == 'bad char'
def test_bad_byte_range():
    with pytest.raises(ValueError) as e: f([256])
    assert str(e.value) == 'bad byte'
def test_bad_byte_negative():
    with pytest.raises(ValueError): f([-1])
def test_bad_byte_bool():
    with pytest.raises(ValueError): f([True])
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
