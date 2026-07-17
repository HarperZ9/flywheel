import pytest
from solution import col_number as f
def test_a(): assert f('A') == 1
def test_z(): assert f('Z') == 26
def test_aa(): assert f('AA') == 27
def test_az(): assert f('AZ') == 52
def test_zz(): assert f('ZZ') == 702
def test_aaa(): assert f('AAA') == 703
def test_empty():
    with pytest.raises(ValueError) as e: f('')
    assert str(e.value) == 'bad label'
def test_lower():
    with pytest.raises(ValueError): f('a')
def test_digit():
    with pytest.raises(ValueError): f('A1')
