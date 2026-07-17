import pytest
from solution import sat_add


def test_no_clamp_within_range():
    assert sat_add(3, 4, 8) == 7
    assert sat_add(100, 27, 8) == 127
    assert sat_add(-100, -28, 8) == -128
    assert sat_add(-5, 5, 8) == 0


def test_clamp_high():
    assert sat_add(100, 100, 8) == 127
    assert sat_add(127, 127, 8) == 127
    assert sat_add(127, 1, 8) == 127


def test_clamp_low():
    assert sat_add(-100, -100, 8) == -128
    assert sat_add(-128, -1, 8) == -128


def test_bits_one_edge():
    assert sat_add(0, 0, 1) == 0
    assert sat_add(0, -1, 1) == -1
    assert sat_add(-1, -1, 1) == -1


def test_bits_invalid_raises():
    with pytest.raises(ValueError):
        sat_add(0, 0, 0)
    with pytest.raises(ValueError):
        sat_add(0, 0, -3)


def test_operand_out_of_range_raises():
    with pytest.raises(ValueError):
        sat_add(128, 0, 8)
    with pytest.raises(ValueError):
        sat_add(0, -129, 8)
    with pytest.raises(ValueError):
        sat_add(1, 0, 1)


def test_bool_rejected():
    with pytest.raises(ValueError):
        sat_add(True, 0, 8)
    with pytest.raises(ValueError):
        sat_add(0, False, 8)
    with pytest.raises(ValueError):
        sat_add(1, 1, True)


def test_non_int_rejected():
    with pytest.raises(ValueError):
        sat_add(1.0, 2, 8)
    with pytest.raises(ValueError):
        sat_add(1, 2, "8")
    with pytest.raises(ValueError):
        sat_add(None, 2, 8)
