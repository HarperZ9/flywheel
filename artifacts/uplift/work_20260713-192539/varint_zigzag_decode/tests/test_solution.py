import pytest
from solution import decode_varints


def test_single_byte_values_zigzag():
    assert decode_varints([0]) == [0]
    assert decode_varints([1]) == [-1]
    assert decode_varints([2]) == [1]
    assert decode_varints([3, 4]) == [-2, 2]
    assert decode_varints([0x7F]) == [-64]


def test_multibyte_value():
    # bytes [0xAC, 0x02] -> unsigned 300 -> signed 150
    assert decode_varints([0xAC, 0x02]) == [150]


def test_multiple_values_and_empty():
    assert decode_varints([]) == []
    assert decode_varints([0xAC, 0x02, 0x01, 0x00]) == [150, -1, 0]


def test_five_byte_varint_ok():
    u = 1 << 28
    assert decode_varints([0x80, 0x80, 0x80, 0x80, 0x01]) == [u >> 1]


def test_truncated():
    with pytest.raises(ValueError, match="truncated"):
        decode_varints([0x80])
    with pytest.raises(ValueError, match="truncated"):
        decode_varints([0x00, 0xFF])


def test_too_long_even_when_stream_ends():
    with pytest.raises(ValueError, match="too long"):
        decode_varints([0x80] * 5)
    with pytest.raises(ValueError, match="too long"):
        decode_varints([0x80, 0x80, 0x80, 0x80, 0x80, 0x01])


def test_overlong_noncanonical():
    with pytest.raises(ValueError, match="overlong"):
        decode_varints([0x80, 0x00])
    with pytest.raises(ValueError, match="overlong"):
        decode_varints([0xFF, 0x80, 0x00])


def test_bad_byte_checked_before_decoding():
    with pytest.raises(ValueError, match="bad byte"):
        decode_varints([256])
    with pytest.raises(ValueError, match="bad byte"):
        decode_varints([-1])
    with pytest.raises(ValueError, match="bad byte"):
        decode_varints([True])
    with pytest.raises(ValueError, match="bad byte"):
        decode_varints([1.0])
    # element validation happens before any decoding error
    with pytest.raises(ValueError, match="bad byte"):
        decode_varints([0x80, 300])


def test_no_mutation():
    data = [0xAC, 0x02, 0x00]
    snap = list(data)
    decode_varints(data)
    assert data == snap
