import pytest
from solution import semver_compare as f
def test_equal(): assert f('1.0.0', '1.0.0') == 0
def test_major(): assert f('1.0.0', '2.0.0') == -1
def test_major_gt(): assert f('2.0.0', '1.0.0') == 1
def test_patch(): assert f('1.0.0', '1.0.1') == -1
def test_pre_lt_release(): assert f('1.0.0-alpha', '1.0.0') == -1
def test_more_ids(): assert f('1.0.0-alpha', '1.0.0-alpha.1') == -1
def test_numeric_lt_alpha(): assert f('1.0.0-alpha.1', '1.0.0-alpha.beta') == -1
def test_ascii_order(): assert f('1.0.0-alpha.beta', '1.0.0-beta') == -1
def test_numeric_ids(): assert f('1.0.0-beta.2', '1.0.0-beta.11') == -1
def test_bad_two_parts():
    with pytest.raises(ValueError) as e: f('1.0', '1.0.0')
    assert str(e.value) == 'bad version'
def test_bad_leading_zero():
    with pytest.raises(ValueError): f('01.0.0', '1.0.0')
def test_bad_pre_leading_zero():
    with pytest.raises(ValueError): f('1.0.0-01', '1.0.0')
