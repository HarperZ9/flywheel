from solution import run_length_encode as f
def test_empty():
    assert f('') == ''
def test_one():
    assert f('a') == 'a1'
def test_runs():
    assert f('aaabbc') == 'a3b2c1'
def test_all_diff():
    assert f('abc') == 'a1b1c1'
def test_all_same():
    assert f('zzzz') == 'z4'
