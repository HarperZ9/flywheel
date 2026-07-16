import pytest
from solution import parse_range_list as f
def test_empty():
    assert f('') == []
def test_mixed():
    assert f('1-3,5,7-9') == [1,2,3,5,7,8,9]
def test_overlap():
    assert f('1-4,3-6,4') == [1,2,3,4,5,6]
def test_spaces():
    assert f(' 2 , 4-5 ') == [2,4,5]
def test_reversed_range():
    with pytest.raises(ValueError):
        f('3-1')
def test_garbage():
    with pytest.raises(ValueError):
        f('1,a')
def test_dangling():
    with pytest.raises(ValueError):
        f('1-')
