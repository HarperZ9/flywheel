import pytest
from solution import decode_frame


def test_valid_frame():
    assert decode_frame("A50301020352") == [1, 2, 3]


def test_lowercase_hex_accepted():
    assert decode_frame("a50301020352") == [1, 2, 3]


def test_empty_payload():
    assert decode_frame("A5005B") == []


def test_odd_length_beats_everything():
    with pytest.raises(ValueError, match="odd length"):
        decode_frame("A50")
    with pytest.raises(ValueError, match="odd length"):
        decode_frame("A5G")  # odd length wins over not hex


def test_not_hex_beats_truncated():
    with pytest.raises(ValueError, match="not hex"):
        decode_frame("A5XX01020352")
    with pytest.raises(ValueError, match="not hex"):
        decode_frame("GG")  # not hex wins over truncated


def test_truncated():
    with pytest.raises(ValueError, match="truncated"):
        decode_frame("A500")
    with pytest.raises(ValueError, match="truncated"):
        decode_frame("")


def test_bad_header():
    with pytest.raises(ValueError, match="bad header"):
        decode_frame("A4005C")


def test_length_mismatch_short_and_long():
    with pytest.raises(ValueError, match="length mismatch"):
        decode_frame("A503010252")  # declares 3 payload bytes, has 2
    with pytest.raises(ValueError, match="length mismatch"):
        decode_frame("A5000052")  # extra byte beyond checksum


def test_bad_checksum():
    with pytest.raises(ValueError, match="bad checksum"):
        decode_frame("A50301020353")
