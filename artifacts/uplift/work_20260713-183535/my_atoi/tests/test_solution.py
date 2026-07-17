from solution import my_atoi as f
def test_plain():
    assert f('42') == 42
def test_ws_neg():
    assert f('   -42') == -42
def test_trailing():
    assert f('4193 with words') == 4193
def test_words():
    assert f('words and 987') == 0
def test_plus():
    assert f('+7') == 7
def test_empty():
    assert f('') == 0
