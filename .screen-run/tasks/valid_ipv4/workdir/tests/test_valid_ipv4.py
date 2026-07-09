from solution import valid_ipv4 as f
def test_ok():
    assert f('192.168.0.1') is True
def test_zero():
    assert f('0.0.0.0') is True
def test_leading_zero():
    assert f('192.168.01.1') is False
def test_too_big():
    assert f('256.1.1.1') is False
def test_three_parts():
    assert f('1.2.3') is False
def test_sign():
    assert f('+1.2.3.4') is False
def test_empty_part():
    assert f('1..2.3') is False
