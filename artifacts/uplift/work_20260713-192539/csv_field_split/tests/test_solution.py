import pytest
from solution import split_csv_line


def test_basic_and_empty_fields():
    assert split_csv_line("a,b,c") == ["a", "b", "c"]
    assert split_csv_line("a,,c") == ["a", "", "c"]


def test_empty_line_single_empty_field():
    assert split_csv_line("") == [""]


def test_trailing_and_leading_comma():
    assert split_csv_line("a,") == ["a", ""]
    assert split_csv_line(",a") == ["", "a"]
    assert split_csv_line(",") == ["", ""]


def test_quoted_field_with_comma_and_escaped_quote():
    assert split_csv_line('"a,b",c') == ["a,b", "c"]
    assert split_csv_line('a,"b""c",d') == ["a", 'b"c', "d"]
    assert split_csv_line('""') == [""]
    assert split_csv_line('""""') == ['"']


def test_whitespace_is_not_stripped():
    assert split_csv_line(" a , b ") == [" a ", " b "]
    assert split_csv_line('" a ",b') == [" a ", "b"]


def test_quote_in_unquoted_field_raises():
    with pytest.raises(ValueError):
        split_csv_line('ab"c')
    with pytest.raises(ValueError):
        split_csv_line(' "a"')


def test_unterminated_quote_raises():
    with pytest.raises(ValueError):
        split_csv_line('"abc')
    with pytest.raises(ValueError):
        split_csv_line('a,"b')
    with pytest.raises(ValueError):
        split_csv_line('"a""')


def test_junk_after_closing_quote_raises():
    with pytest.raises(ValueError):
        split_csv_line('"a"b')
    with pytest.raises(ValueError):
        split_csv_line('"a" ,b')
