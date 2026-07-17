import pytest
from solution import ipv4_to_int as f
def test_zero(): assert f('0.0.0.0') == 0
def test_broadcast(): assert f('255.255.255.255') == 4294967295
def test_sequential(): assert f('1.2.3.4') == 16909060
def test_common(): assert f('192.168.0.1') == 3232235521
def test_ten(): assert f('10.0.0.1') == 167772161
def test_leading_zero():
    with pytest.raises(ValueError) as e: f('192.168.01.1')
    assert str(e.value) == 'bad address'
def test_too_big():
    with pytest.raises(ValueError): f('256.0.0.1')
def test_three_parts():
    with pytest.raises(ValueError): f('1.2.3')
def test_empty_part():
    with pytest.raises(ValueError): f('1..2.3')
def test_sign():
    with pytest.raises(ValueError): f('+1.2.3.4')
