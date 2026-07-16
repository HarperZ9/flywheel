from solution import longest_common_prefix as f
def test_common():
    assert f(['flower','flow','flight']) == 'fl'
def test_none():
    assert f(['dog','cat']) == ''
def test_empty_list():
    assert f([]) == ''
def test_one():
    assert f(['alone']) == 'alone'
def test_empty_str():
    assert f(['','abc']) == ''
