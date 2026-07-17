import pytest
from solution import parse_template_fields


def test_plain_text():
    assert parse_template_fields("hello") == [("text", "hello")]


def test_empty():
    assert parse_template_fields("") == []


def test_fields():
    assert parse_template_fields("{a}") == [("field", "a")]
    assert parse_template_fields("x{name}y") == [
        ("text", "x"),
        ("field", "name"),
        ("text", "y"),
    ]
    assert parse_template_fields("{a}{b}") == [("field", "a"), ("field", "b")]


def test_name_charset_ok():
    assert parse_template_fields("{_a1}") == [("field", "_a1")]
    assert parse_template_fields("{A_b_2}") == [("field", "A_b_2")]


def test_brace_escapes_merge_maximal():
    assert parse_template_fields("{{") == [("text", "{")]
    assert parse_template_fields("a{{b}}c") == [("text", "a{b}c")]
    assert parse_template_fields("{{{x}}}") == [
        ("text", "{"),
        ("field", "x"),
        ("text", "}"),
    ]
    assert parse_template_fields("{a}}}b") == [("field", "a"), ("text", "}b")]


def test_bad_names_raise():
    for bad in ["{}", "{1a}", "{a-b}", "{a b}", "{a.b}"]:
        with pytest.raises(ValueError):
            parse_template_fields(bad)


def test_unterminated_raises():
    for bad in ["{", "abc{name", "{a}{"]:
        with pytest.raises(ValueError):
            parse_template_fields(bad)


def test_stray_brace_raises():
    for bad in ["}", "a}b", "{a}}"]:
        with pytest.raises(ValueError):
            parse_template_fields(bad)
