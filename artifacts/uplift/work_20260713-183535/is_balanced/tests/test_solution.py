from solution import is_balanced as f
def test_empty():
    assert f('') is True
def test_ok():
    assert f('()[]{}') is True
def test_nested():
    assert f('{[()]}') is True
def test_mismatch():
    assert f('(]') is False
def test_interleave():
    assert f('([)]') is False
def test_unclosed():
    assert f('(((') is False
