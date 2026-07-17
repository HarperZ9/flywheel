import pytest
from solution import outline_paths


def test_forest_and_leaf_order():
    lines = ["a", "  b", "    c", "  d", "e"]
    assert outline_paths(lines) == ["a/b/c", "a/d", "e"]


def test_blank_and_whitespace_lines_skipped_without_breaking_levels():
    lines = ["a", "", "   ", "\t", "  b"]
    assert outline_paths(lines) == ["a/b"]


def test_trailing_ws_stripped_inner_spaces_kept():
    lines = ["top node  ", "  child x "]
    assert outline_paths(lines) == ["top node/child x"]


def test_empty_and_all_blank():
    assert outline_paths([]) == []
    assert outline_paths(["", "  "]) == []


def test_indent_jump_including_indented_first_line():
    with pytest.raises(ValueError, match="indent jump"):
        outline_paths(["a", "    b"])
    with pytest.raises(ValueError, match="indent jump"):
        outline_paths(["  a"])


def test_odd_indent():
    with pytest.raises(ValueError, match="odd indent"):
        outline_paths(["a", "   b"])


def test_tab_in_indent_checked_before_width():
    with pytest.raises(ValueError, match="tab in indent"):
        outline_paths(["a", " \tb"])


def test_slash_in_name():
    with pytest.raises(ValueError, match="slash in name"):
        outline_paths(["a/b"])


def test_no_mutation():
    lines = ["a", "  b"]
    snap = list(lines)
    outline_paths(lines)
    assert lines == snap
