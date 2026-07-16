from solution import roman_to_int as f
def test_simple():
    assert f('III') == 3
def test_sub_iv():
    assert f('IV') == 4
def test_sub_ix():
    assert f('IX') == 9
def test_lviii():
    assert f('LVIII') == 58
def test_big():
    assert f('MCMXCIV') == 1994
