import pytest
from solution import tokenize_quoted


def test_whitespace_split():
    assert tokenize_quoted("a b\tc") == ["a", "b", "c"]
    assert tokenize_quoted("  a   b  ") == ["a", "b"]


def test_empty_and_blank():
    assert tokenize_quoted("") == []
    assert tokenize_quoted(" \t ") == []


def test_double_quotes():
    assert tokenize_quoted('"a b"') == ["a b"]
    assert tokenize_quoted('x "a b" y') == ["x", "a b", "y"]


def test_double_quote_escapes():
    assert tokenize_quoted('"a\\"b"') == ['a"b']
    assert tokenize_quoted('"a\\\\b"') == ["a\\b"]


def test_single_quotes_literal():
    assert tokenize_quoted("'a b'") == ["a b"]
    assert tokenize_quoted("'a\\b'") == ["a\\b"]
    assert tokenize_quoted("'\"'") == ['"']


def test_concatenation():
    assert tokenize_quoted('a"b c"d') == ["ab cd"]
    assert tokenize_quoted("a'b'\"c\"") == ["abc"]


def test_empty_token_from_quotes():
    assert tokenize_quoted('""') == [""]
    assert tokenize_quoted("a '' b") == ["a", "", "b"]


def test_bare_backslash_escapes():
    assert tokenize_quoted("a\\ b") == ["a b"]
    assert tokenize_quoted("\\'x") == ["'x"]


def test_error_contracts():
    with pytest.raises(ValueError):
        tokenize_quoted('"abc')
    with pytest.raises(ValueError):
        tokenize_quoted("'abc")
    with pytest.raises(ValueError):
        tokenize_quoted('"a\\"')
    with pytest.raises(ValueError):
        tokenize_quoted('"a\\nb"')
    with pytest.raises(ValueError):
        tokenize_quoted("abc\\")
