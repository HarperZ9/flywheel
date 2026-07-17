import pytest
from solution import untilde


def test_plain_and_simple_escapes():
    assert untilde("") == ""
    assert untilde("ab") == "ab"
    assert untilde("a~nb~tc") == "a\nb\tc"
    assert untilde("~~") == "~"
    assert untilde("~~n") == "~n"


def test_hex_escape_exactly_two_digits():
    assert untilde("~x41") == "A"
    assert untilde("~x0a") == "\n"
    assert untilde("~x0A") == "\n"
    assert untilde("~x123") == "\x12" + "3"


def test_hex_may_produce_control_chars():
    assert untilde("~x00") == "\x00"
    assert untilde("~x1f") == "\x1f"


def test_dangling_escape():
    with pytest.raises(ValueError, match="dangling escape"):
        untilde("abc~")


def test_bad_escape_case_sensitive():
    with pytest.raises(ValueError, match="bad escape"):
        untilde("~q")
    with pytest.raises(ValueError, match="bad escape"):
        untilde("~N")
    with pytest.raises(ValueError, match="bad escape"):
        untilde("~X41")


def test_bad_hex():
    with pytest.raises(ValueError, match="bad hex"):
        untilde("~x")
    with pytest.raises(ValueError, match="bad hex"):
        untilde("~x4")
    with pytest.raises(ValueError, match="bad hex"):
        untilde("~x4G")
    with pytest.raises(ValueError, match="bad hex"):
        untilde("~xg1")


def test_raw_control_forbidden():
    with pytest.raises(ValueError, match="raw control"):
        untilde("a\nb")
    with pytest.raises(ValueError, match="raw control"):
        untilde("a\tb")


def test_first_error_in_scan_order_wins():
    with pytest.raises(ValueError, match="raw control"):
        untilde("a\n~")  # raw control at index 1 beats dangling ~ at end
    with pytest.raises(ValueError, match="bad escape"):
        untilde("~q\n")  # bad escape at index 0 beats raw control later
