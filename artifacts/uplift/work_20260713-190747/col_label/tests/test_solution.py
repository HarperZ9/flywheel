import pytest
from solution import col_label as f
def test_a(): assert f(1) == 'A'
def test_z(): assert f(26) == 'Z'
def test_aa(): assert f(27) == 'AA'
def test_az(): assert f(52) == 'AZ'
def test_ba(): assert f(53) == 'BA'
def test_zz(): assert f(702) == 'ZZ'
def test_aaa(): assert f(703) == 'AAA'
def test_bad_zero():
    with pytest.raises(ValueError) as e: f(0)
    assert str(e.value) == 'bad column'
def test_bool():
    with pytest.raises(ValueError): f(True)
