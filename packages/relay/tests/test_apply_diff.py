"""apply_diff: a strict, fail-closed unified-diff applier. Unlike aider's fuzzy
context match, a hunk whose context does not match the current file EXACTLY is
refused with nothing written, and the new write path is covered by the same guards
as the other edit tools (protected-file and reward-hack scans see the added lines)."""

import json

from relay.integrity import trajectory_integrity
from relay.local_session import SessionLedger
from relay.local_tools import WRITE_TOOLS, ToolExecutor, ToolGate, edited_targets
from relay.udiff import apply_udiff, parse_hunks


def _ex(tmp_path):
    return ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))


def _led(name, args):
    led = SessionLedger()
    led.append("user", "goal")
    led.append("tool_call", f"{name} {json.dumps(args)}")
    return led


# --- pure parse + apply ---------------------------------------------------

def test_parse_hunks_splits_context_removed_and_added():
    hunks, err = parse_hunks("@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n")
    assert err is None and len(hunks) == 1
    assert hunks[0]["pre"] == ["a", "b", "c"] and hunks[0]["post"] == ["a", "B", "c"]


def test_apply_replaces_a_line():
    new, err = apply_udiff("a\nb\nc\n", parse_hunks("@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n")[0])
    assert err is None and new == "a\nB\nc\n"


def test_apply_inserts_and_deletes():
    ins, _ = apply_udiff("a\nb\nc\n", parse_hunks("@@ -1,3 +1,4 @@\n a\n b\n+X\n c\n")[0])
    assert ins == "a\nb\nX\nc\n"
    dele, _ = apply_udiff("a\nb\nc\n", parse_hunks("@@ -1,3 +1,2 @@\n a\n-b\n c\n")[0])
    assert dele == "a\nc\n"


def test_a_drifted_context_is_refused_no_fuzz():
    new, err = apply_udiff("a\nb\nc\n", parse_hunks("@@ -1,3 +1,3 @@\n a\n-ZZZ\n+B\n c\n")[0])
    assert new is None and "did not match" in err


# --- executor tool --------------------------------------------------------

def test_apply_diff_tool_edits_the_file(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    r = _ex(tmp_path).execute("apply_diff", {"path": "m.py",
             "diff": "@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 9\n"})
    assert r.ok and (tmp_path / "m.py").read_text() == "x = 1\ny = 9\n"


def test_apply_diff_refuses_and_leaves_the_file_untouched(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    r = _ex(tmp_path).execute("apply_diff", {"path": "m.py",
             "diff": "@@ -1,2 +1,2 @@\n x = 1\n-y = 7\n+y = 9\n"})   # y = 7 does not exist
    assert not r.ok and (tmp_path / "m.py").read_text() == "x = 1\ny = 2\n"


def test_apply_diff_applies_multiple_hunks(tmp_path):
    (tmp_path / "m.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    diff = "@@ -1,2 +1,2 @@\n a\n-b\n+B\n@@ -4,2 +4,2 @@\n d\n-e\n+E\n"
    r = _ex(tmp_path).execute("apply_diff", {"path": "m.py", "diff": diff})
    assert r.ok and (tmp_path / "m.py").read_text() == "a\nB\nc\nd\nE\n"


def test_apply_diff_is_gated_like_write(tmp_path):
    (tmp_path / "m.py").write_text("k = 1\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = ex.execute("apply_diff", {"path": "m.py", "diff": "@@ -1 +1 @@\n-k = 1\n+k = 2\n"})
    assert not r.ok and "[gate]" in r.output
    assert (tmp_path / "m.py").read_text() == "k = 1\n"


# --- no blind spot: the same guards cover the diff surface -----------------

def test_apply_diff_is_in_the_canonical_write_set():
    assert "apply_diff" in WRITE_TOOLS


def test_edited_targets_returns_only_the_added_lines():
    args = {"path": "a.py", "diff": "@@ -1 +1,2 @@\n keep\n-gone\n+added_one\n+added_two\n"}
    assert edited_targets("apply_diff", args) == [("a.py", "added_one\nadded_two")]


def test_editing_a_protected_file_via_apply_diff_is_flagged():
    led = _led("apply_diff", {"path": "tests/test_core.py",
               "diff": "@@ -1 +1 @@\n-assert x\n+pass\n"})
    assert any(f.kind == "edited_protected_file" for f in trajectory_integrity(led))


def test_reward_hacking_in_added_lines_is_flagged():
    led = _led("apply_diff", {"path": "app.py",
               "diff": "@@ -1 +1,2 @@\n keep\n+import pytest\n+pytestmark = pytest.mark.skip\n"})
    assert any("skip" in f.kind for f in trajectory_integrity(led))
