"""Harness trees: the editable surface, digests, diffs and component restriction."""
import pytest

from harness import self_improve_tree as st


def test_component_granularity():
    assert st.component_of("systemprompt.md") == "systemprompt.md"
    assert st.component_of("scripts/check.py") == "scripts/check.py"
    assert st.component_of("skills/review/SKILL.md") == "skills/review"


@pytest.mark.parametrize("bad", ["../x.md", "/etc/passwd", "notes.txt", "scripts",
                                 "systemprompt.md/child", "scripts\\a.py", ""])
def test_off_surface_paths_are_refused(bad):
    with pytest.raises(st.TreeError):
        st.component_of(bad)


def test_digest_is_order_independent_and_content_bound():
    a = {"systemprompt.md": "x", "scripts/a.py": "1"}
    b = {"scripts/a.py": "1", "systemprompt.md": "x"}
    assert st.digest(a) == st.digest(b)
    assert st.digest(a) != st.digest({**a, "scripts/a.py": "2"})


def test_diff_and_changed_components():
    parent = {"systemprompt.md": "a\n", "scripts/a.py": "x\n"}
    child = {"systemprompt.md": "a\n", "scripts/a.py": "y\n", "scripts/b.py": "z\n"}
    diff = st.unified_diff(parent, child)
    assert "-x" in diff and "+y" in diff and "+++ b/scripts/b.py" in diff
    assert st.changed_components(parent, child) == ["scripts/a.py", "scripts/b.py"]
    assert st.unified_diff(parent, parent) == ""


def test_restrict_applies_only_named_components():
    parent = {"scripts/a.py": "1", "scripts/b.py": "1"}
    child = {"scripts/a.py": "2", "scripts/b.py": "2"}
    assert st.restrict(parent, child, ["scripts/a.py"]) == {"scripts/a.py": "2",
                                                            "scripts/b.py": "1"}


def test_restrict_handles_added_and_removed_files():
    parent = {"scripts/a.py": "1", "scripts/gone.py": "x"}
    child = {"scripts/a.py": "1", "scripts/new.py": "n"}
    out = st.restrict(parent, child, ["scripts/gone.py", "scripts/new.py"])
    assert out == {"scripts/a.py": "1", "scripts/new.py": "n"}


def test_verification_surface_flag():
    assert st.touches_verification(["checks/self.py"])
    assert not st.touches_verification(["scripts/check.py"])


def test_write_read_roundtrip_and_smuggled_file(tmp_path):
    tree = {"systemprompt.md": "p", "skills/r/SKILL.md": "s"}
    st.write_tree(tree, tmp_path / "h")
    assert st.read_tree(tmp_path / "h") == tree
    (tmp_path / "h" / "stray.txt").write_text("x")
    with pytest.raises(st.TreeError):
        st.read_tree(tmp_path / "h")
