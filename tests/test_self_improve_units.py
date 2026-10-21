"""Change units: line, hunk and file granularity, and subset application."""
import pytest

from harness import self_improve_units as su

PARENT = {"scripts/a.py": "one\ntwo\nthree\n", "systemprompt.md": "p\n"}
CHILD = {"scripts/a.py": "one\nTWO\nthree\nfour\n", "scripts/new.py": "n\n",
         "systemprompt.md": "p\n"}


def test_units_at_each_granularity():
    assert su.change_units(PARENT, CHILD, "file") == ["scripts/a.py#file", "scripts/new.py#file"]
    assert su.change_units(PARENT, CHILD, "hunk") == ["scripts/a.py@0", "scripts/a.py@1",
                                                      "scripts/new.py#file"]
    assert su.change_units(PARENT, CHILD, "line") == [
        "scripts/a.py#-1", "scripts/a.py#+1", "scripts/a.py#+3", "scripts/new.py#file"]


def test_all_units_rebuild_the_child_and_none_the_parent():
    for g in su.GRANULARITIES:
        assert su.apply_units(PARENT, CHILD, su.change_units(PARENT, CHILD, g)) == CHILD
        assert su.apply_units(PARENT, CHILD, []) == PARENT


def test_subsets_apply_independently():
    only_insert = su.apply_units(PARENT, CHILD, ["scripts/a.py#+3"])
    assert only_insert["scripts/a.py"] == "one\ntwo\nthree\nfour\n"
    only_delete = su.apply_units(PARENT, CHILD, ["scripts/a.py#-1"])
    assert only_delete["scripts/a.py"] == "one\nthree\n"
    assert "scripts/new.py" not in only_delete


def test_removed_file_is_one_unit():
    removed = {"systemprompt.md": "p\n"}
    assert su.change_units(PARENT, removed, "line") == ["scripts/a.py#file"]
    assert su.apply_units(PARENT, removed, ["scripts/a.py#file"]) == removed


def test_unit_tree_nests_lines_in_hunks_in_files():
    tree = su.unit_tree(PARENT, CHILD)
    assert tree[0] == ("scripts/a.py#file", [("scripts/a.py@0", ["scripts/a.py#-1",
                                                                  "scripts/a.py#+1"]),
                                             ("scripts/a.py@1", ["scripts/a.py#+3"])])
    assert tree[1] == ("scripts/new.py#file", [])


def test_unit_component_and_bad_granularity():
    assert su.unit_component("scripts/a.py#+3") == "scripts/a.py"
    assert su.unit_component("skills/r/SKILL.md@0") == "skills/r"
    with pytest.raises(ValueError):
        su.change_units(PARENT, CHILD, "word")
