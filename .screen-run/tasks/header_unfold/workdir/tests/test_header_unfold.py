import pytest
from solution import unfold_headers


def test_basic():
    assert unfold_headers(["Host: example.com", "Content-Type: text/plain"]) == [
        ("host", "example.com"),
        ("content-type", "text/plain"),
    ]


def test_unfolding():
    assert unfold_headers(["Subject: hello", "\tworld", "X-A: 1"]) == [
        ("subject", "hello world"),
        ("x-a", "1"),
    ]
    assert unfold_headers(["A: x", "  y  ", " z"]) == [("a", "x y z")]


def test_value_whitespace_and_empty_value():
    assert unfold_headers(["A:   spaced   "]) == [("a", "spaced")]
    assert unfold_headers(["A:"]) == [("a", "")]
    assert unfold_headers(["A:", " x"]) == [("a", "x")]


def test_case_and_duplicates():
    assert unfold_headers(["FOO: 1", "foo: 2", "FoO: 3"]) == [
        ("foo", "1"),
        ("foo", "2"),
        ("foo", "3"),
    ]


def test_empty_input():
    assert unfold_headers([]) == []


def test_no_mutation():
    lines = ["A: 1", " cont", "B: 2"]
    snapshot = list(lines)
    unfold_headers(lines)
    assert lines == snapshot


def test_continuation_first_raises():
    with pytest.raises(ValueError):
        unfold_headers([" x: 1"])
    with pytest.raises(ValueError):
        unfold_headers(["\tfolded"])


def test_missing_colon_raises():
    with pytest.raises(ValueError):
        unfold_headers(["abc"])
    with pytest.raises(ValueError):
        unfold_headers(["A: 1", ""])


def test_bad_name_raises():
    for bad in [[": v"], ["a b: v"], ["a_b: v"], ["Host : v"]]:
        with pytest.raises(ValueError):
            unfold_headers(bad)


def test_blank_continuation_raises():
    with pytest.raises(ValueError):
        unfold_headers(["A: 1", "   "])
