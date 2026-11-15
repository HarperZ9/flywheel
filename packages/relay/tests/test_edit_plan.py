"""edit_plan: transactional multi-file hash-anchored edits, all-or-nothing, each op
carrying a re-derivable receipt. These falsifiers prove the batch applies atomically
or not at all, one stale anchor refuses the WHOLE plan with the tree untouched, and
the multi-file edit surface is covered by the same guards as the single-file tools.
edit_plan's ops[].path is NOT a blind spot for integrity, cert, or the witnessed diff."""

import json

from relay.cert import _edited_paths
from relay.edit_plan import check_overlaps
from relay.hashline import line_anchor
from relay.integrity import trajectory_integrity
from relay.local_loop import witnessed_edit_paths
from relay.local_session import SessionLedger
from relay.local_tools import WRITE_TOOLS, ToolExecutor, ToolGate, edited_targets


def _ex(tmp_path):
    return ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))


def _anchor(ex, path, needle):
    view = ex.execute("read_file", {"path": path, "hashed": True}).output
    for row in view.splitlines():
        h, _, body = row.partition("|")
        if needle in body:
            return h
    raise AssertionError(f"{needle!r} not in hashed view of {path}")


def _receipt(result_output):
    return json.loads(result_output.split("\n", 1)[1])["receipt"]


def _led(*calls):
    led = SessionLedger()
    led.append("user", "goal")
    for name, args in calls:
        led.append("tool_call", f"{name} {json.dumps(args)}")
    return led


# --- transactional apply --------------------------------------------------

def test_applies_ops_across_two_files_atomically(tmp_path):
    (tmp_path / "a.py").write_text("a1\na2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b1\nb2\n", encoding="utf-8")
    ex = _ex(tmp_path)
    ops = [
        {"path": "a.py", "at": _anchor(ex, "a.py", "a2"), "new": "A2"},
        {"path": "b.py", "after": _anchor(ex, "b.py", "b1"), "new": "bX"},
    ]
    r = ex.execute("edit_plan", {"ops": ops})
    assert r.ok
    assert (tmp_path / "a.py").read_text() == "a1\nA2\n"
    assert (tmp_path / "b.py").read_text() == "b1\nbX\nb2\n"
    assert len(_receipt(r.output)) == 2


def test_multiple_ops_on_one_file_do_not_shift_each_other(tmp_path):
    (tmp_path / "m.py").write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")
    ex = _ex(tmp_path)
    ops = [
        {"path": "m.py", "at": _anchor(ex, "m.py", "l1"), "new": "L1"},
        {"path": "m.py", "at": _anchor(ex, "m.py", "l3"), "new": ""},        # delete
        {"path": "m.py", "after": _anchor(ex, "m.py", "l4"), "new": "l5"},   # append
    ]
    r = ex.execute("edit_plan", {"ops": ops})
    assert r.ok and (tmp_path / "m.py").read_text() == "L1\nl2\nl4\nl5\n"


# --- all-or-nothing -------------------------------------------------------

def test_one_stale_anchor_refuses_the_whole_batch(tmp_path):
    (tmp_path / "a.py").write_text("a1\na2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b1\nb2\n", encoding="utf-8")
    ex = _ex(tmp_path)
    ops = [
        {"path": "a.py", "at": _anchor(ex, "a.py", "a2"), "new": "A2"},   # valid
        {"path": "b.py", "at": "deadbeef", "new": "B2"},                  # stale
    ]
    r = ex.execute("edit_plan", {"ops": ops})
    assert not r.ok and "not found" in r.output
    assert (tmp_path / "a.py").read_text() == "a1\na2\n"      # untouched
    assert (tmp_path / "b.py").read_text() == "b1\nb2\n"      # untouched


def test_overlapping_ops_on_one_file_are_refused(tmp_path):
    (tmp_path / "m.py").write_text("x\ny\nz\n", encoding="utf-8")
    ex = _ex(tmp_path)
    ax, ay = _anchor(ex, "m.py", "x"), _anchor(ex, "m.py", "y")
    ops = [
        {"path": "m.py", "at": ax, "end": ay, "new": "XY"},   # covers x..y
        {"path": "m.py", "at": ay, "new": "Y"},               # y again -> overlap
    ]
    r = ex.execute("edit_plan", {"ops": ops})
    assert not r.ok and "overlap" in r.output
    assert (tmp_path / "m.py").read_text() == "x\ny\nz\n"     # untouched


def test_two_inserts_at_the_same_point_are_refused():
    edits = [
        {"lo": 3, "hi": 3, "op_index": 0},
        {"lo": 3, "hi": 3, "op_index": 1},
    ]
    assert check_overlaps(edits) is not None


# --- re-derivable receipt -------------------------------------------------

def test_receipt_anchors_recompute_from_the_pre_image(tmp_path):
    (tmp_path / "m.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    ex = _ex(tmp_path)
    ops = [{"path": "m.py", "at": _anchor(ex, "m.py", "two"), "new": "TWO"}]
    r = ex.execute("edit_plan", {"ops": ops})
    for rec in _receipt(r.output):
        assert line_anchor(rec["line"], rec["pre_image"]) == rec["anchor"]   # stranger re-derives


# --- gate + malformed -----------------------------------------------------

def test_edit_plan_is_gated_like_write(tmp_path):
    (tmp_path / "m.py").write_text("k = 1\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = ex.execute("edit_plan", {"ops": [{"path": "m.py", "at": "abc", "new": "k = 2"}]})
    assert not r.ok and "[gate]" in r.output
    assert (tmp_path / "m.py").read_text() == "k = 1\n"


def test_empty_ops_is_refused(tmp_path):
    r = _ex(tmp_path).execute("edit_plan", {"ops": []})
    assert not r.ok and "non-empty" in r.output


def test_op_without_a_path_is_refused(tmp_path):
    r = _ex(tmp_path).execute("edit_plan", {"ops": [{"at": "abc", "new": "z"}]})
    assert not r.ok and "missing 'path'" in r.output


# --- no blind spot: the same guards cover the multi-file surface ----------

def test_edit_plan_is_in_the_canonical_write_set():
    assert "edit_plan" in WRITE_TOOLS


def test_edited_targets_lists_every_op_path_and_new():
    args = {"ops": [{"path": "a.py", "new": "x"}, {"path": "b.py", "new": "y"}]}
    assert edited_targets("edit_plan", args) == [("a.py", "x"), ("b.py", "y")]


def test_a_protected_file_edited_via_edit_plan_is_flagged():
    led = _led(("edit_plan", {"ops": [
        {"path": "src/ok.py", "at": "a1", "new": "fine"},
        {"path": "tests/test_core.py", "at": "a2", "new": "pass"},   # protected
    ]}))
    flags = trajectory_integrity(led)
    assert any(f.kind == "edited_protected_file" and "test_core" in f.detail for f in flags)


def test_reward_hacking_in_any_op_is_flagged():
    led = _led(("edit_plan", {"ops": [
        {"path": "a.py", "at": "a1", "new": "clean = 1"},
        {"path": "b.py", "at": "a2", "new": "import pytest\npytestmark = pytest.mark.skip"},
    ]}))
    flags = trajectory_integrity(led)
    assert any("skip" in f.kind for f in flags)


def test_every_edit_plan_path_is_witnessed_and_certified():
    led = _led(("edit_plan", {"ops": [
        {"path": "a.py", "at": "a1", "new": "x"},
        {"path": "b.py", "after": "a2", "new": "y"},
    ]}))
    assert witnessed_edit_paths(led) == ["a.py", "b.py"]    # a commit can bind both
    assert set(_edited_paths(led)) == {"a.py", "b.py"}       # both enter the .rvc
