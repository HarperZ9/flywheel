import pytest
from solution import evaluate_rpn as f
def test_simple():
    assert f(['2','3','+']) == 5
def test_trunc_toward_zero():
    assert f(['-7','2','/']) == -3
def test_nested():
    assert f(['4','13','5','/','+']) == 6
def test_too_few():
    with pytest.raises(ValueError):
        f(['+'])
def test_leftover():
    with pytest.raises(ValueError):
        f(['1','2'])
def test_div0():
    with pytest.raises(ValueError):
        f(['1','0','/'])
