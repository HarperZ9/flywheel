"""test_agent_tools.py — the new built-in tools: grep, glob, apply_patch.

Success criteria:
  - grep finds matching lines as file:line:text; a bad regex errors cleanly.
  - glob lists matching paths under the sandbox root.
  - apply_patch round-trips a difflib-generated diff, creates new files, and
    refuses (without corrupting) a stale patch; it is gated behind allow_write.
  - the exec denylist blocks destructive rm/rmdir in ANY flag ordering.
  - grep/glob never read or list a file whose real path escapes the root
    (a symlink or junction out of the tree is skipped).
"""
import difflib
import os
import subprocess

import pytest

from harness.local_tools import ToolExecutor, ToolGate


def _link_outside(root, outside):
    """Best-effort in-tree link pointing outside the sandbox. Returns the link
    path, or None (caller skips) when the platform grants no way to make one."""
    link = os.path.join(str(root), "linked")
    try:
        os.symlink(str(outside), link, target_is_directory=True)
        return link
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name == "nt":                       # junctions need no privilege
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, str(outside)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return link
    return None


def _diff(old: str, new: str, path: str = "f.txt") -> str:
    return "\n".join(difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"a/{path}", f"b/{path}", lineterm=""))


def test_grep_finds_matches(tmp_path):
    (tmp_path / "a.py").write_text("import os\nx = 1\ndef go():\n    return x\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nothing here\n", encoding="utf-8")
    out = ToolExecutor(root=str(tmp_path)).execute("grep", {"pattern": r"def \w+", "glob": "*.py"})
    assert out.ok and "a.py:3:def go():" in out.output


def test_grep_bad_regex_errors():
    out = ToolExecutor(root=".").execute("grep", {"pattern": "("})
    assert not out.ok and "bad regex" in out.output


def test_glob_lists_paths(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("x", encoding="utf-8")
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")
    out = ToolExecutor(root=str(tmp_path)).execute("glob", {"pattern": "**/*.py"})
    assert out.ok and "pkg/m.py" in out.output and "readme.md" not in out.output


def test_apply_patch_roundtrips_a_difflib_diff(tmp_path):
    old = "line1\nline2\nline3\n"
    new = "line1\nline2 changed\nline3\nline4\n"
    (tmp_path / "f.txt").write_text(old, encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    out = ex.execute("apply_patch", {"patch": _diff(old, new)})
    assert out.ok, out.output
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == new


def test_apply_patch_creates_a_new_file(tmp_path):
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    new = "hello\nworld\n"
    # a real new-file diff is from an empty file (@@ -0,0 ... @@)
    diff = "\n".join(difflib.unified_diff(
        [], new.split("\n"), "a/new.txt", "b/new.txt", lineterm="")).replace(
        "--- a/new.txt", "--- /dev/null")
    out = ex.execute("apply_patch", {"patch": diff})
    assert out.ok, out.output
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == new


def test_apply_patch_refuses_stale_patch_without_corrupting(tmp_path):
    (tmp_path / "f.txt").write_text("actual content\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    # a diff whose context does not match the file
    stale = _diff("expected content\n", "changed\n", "f.txt")
    out = ex.execute("apply_patch", {"patch": stale})
    assert not out.ok and "mismatch" in out.output
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "actual content\n"   # untouched


def test_apply_patch_gated_by_allow_write(tmp_path):
    (tmp_path / "f.txt").write_text("a\n", encoding="utf-8")
    out = ToolExecutor(root=str(tmp_path)).execute("apply_patch", {"patch": _diff("a\n", "b\n")})
    assert not out.ok and "[gate]" in out.output


@pytest.mark.parametrize("cmd", [
    "rm -rf /x", "rm -fr /x", "rm -r -f /x", "rm --recursive --force /x",
    "rm -Rf /x", "rmdir /s /q c:\\x", "rmdir /q /s c:\\x",
])
def test_denylist_blocks_destructive_rm_in_any_flag_order(cmd):
    # the guardrail must not depend on the exact literal flag ordering; every
    # spelling of a recursive-force delete is refused even when exec is allowed
    denied = ToolGate(allow_exec=True).check("run", {"cmd": cmd})
    assert denied == "command blocked by denylist", cmd


def test_denylist_leaves_a_benign_command_alone():
    assert ToolGate(allow_exec=True).check("run", {"cmd": "rm one_file.txt"}) is None
    assert ToolGate(allow_exec=True).check("run", {"cmd": "python -m pytest -q"}) is None


def test_grep_does_not_read_a_file_linked_outside_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOPSECRET marker", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "normal.txt").write_text("TOPSECRET marker in-tree", encoding="utf-8")
    if _link_outside(root, outside) is None:
        pytest.skip("platform grants no symlink/junction without privilege")
    out = ToolExecutor(root=str(root)).execute("grep", {"pattern": "TOPSECRET"})
    assert out.ok
    assert "normal.txt" in out.output          # the in-tree hit is returned
    assert "secret.txt" not in out.output      # the escaped file is NOT read


def test_glob_does_not_list_a_file_linked_outside_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "normal.txt").write_text("x", encoding="utf-8")
    if _link_outside(root, outside) is None:
        pytest.skip("platform grants no symlink/junction without privilege")
    out = ToolExecutor(root=str(root)).execute("glob", {"pattern": "**/*.txt"})
    assert out.ok
    assert "normal.txt" in out.output
    assert "secret.txt" not in out.output
