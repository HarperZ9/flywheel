"""Hash-anchored edits: the model reads a file with per-line anchors, then edits by
anchor instead of by repeating line text. These falsifiers prove the anchor pins to
the intended line, a stale anchor is refused so an edit fails closed instead of
landing on the wrong line, and the new write path carries the same gate and the same
integrity guards as the older edit tools. It is a new tool, not a new blind spot."""

from relay.hashline import annotate_hashed, find_anchor, line_anchor
from relay.integrity import trajectory_integrity
from relay.local_session import SessionLedger
from relay.local_tools import WRITE_TOOLS, ToolExecutor, ToolGate


def _ex(tmp_path):
    return ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))


def _anchor_of(ex, path, needle):
    """The anchor of the first line containing `needle`, read from the hashed view."""
    view = ex.execute("read_file", {"path": path, "hashed": True}).output
    for row in view.splitlines():
        h, _, body = row.partition("|")
        if needle in body:
            return h
    raise AssertionError(f"{needle!r} not found in hashed view:\n{view}")


def _led(*calls):
    led = SessionLedger()
    led.append("user", "goal")
    for name, blob in calls:
        led.append("tool_call", f"{name} {blob}")
    return led


# --- the anchor primitive -------------------------------------------------

def test_anchor_is_deterministic_and_folds_in_position():
    assert line_anchor(1, "a = 1") == line_anchor(1, "a = 1")     # stable
    assert line_anchor(1, "a = 1") != line_anchor(2, "a = 1")     # position matters
    assert line_anchor(1, "a = 1") != line_anchor(1, "a = 2")     # content matters


def test_identical_lines_get_distinct_anchors():
    view = annotate_hashed("x = 0\nx = 0\n")
    anchors = [row.split("|", 1)[0] for row in view.splitlines()]
    assert anchors[0] != anchors[1]      # duplicate lines are still addressable


def test_hashed_view_round_trips_to_the_original_bytes():
    body = "def f():\n    return a | b\n\nlast"      # a line that contains '|'
    rebuilt = "".join(row.split("|", 1)[1] for row in
                      annotate_hashed(body).splitlines(keepends=True))
    assert rebuilt == body


def test_find_anchor_reports_miss():
    lines = ["a\n", "b\n"]
    assert find_anchor(lines, line_anchor(2, "b")) == 1
    assert find_anchor(lines, "00000000") == -1


def test_find_anchor_reports_ambiguity(monkeypatch):
    # Force a truncation collision so two lines share one anchor; the resolver must
    # report it (-2) rather than silently picking one.
    monkeypatch.setattr("relay.hashline.line_anchor", lambda n, s: "dead")
    assert find_anchor(["a\n", "b\n"], "dead") == -2


# --- the read view --------------------------------------------------------

def test_hashed_read_is_opt_in(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    ex = _ex(tmp_path)
    assert ex.execute("read_file", {"path": "m.py"}).output == "a = 1\nb = 2\n"
    hashed = ex.execute("read_file", {"path": "m.py", "hashed": True}).output
    assert hashed.splitlines()[0].endswith("|a = 1")
    assert hashed != "a = 1\nb = 2\n"


# --- replace / insert / delete -------------------------------------------

def test_replace_one_line_by_anchor(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    ex = _ex(tmp_path)
    at = _anchor_of(ex, "m.py", "b = 2")
    r = ex.execute("edit_lines", {"path": "m.py", "at": at, "new": "b = 9"})
    assert r.ok and (tmp_path / "m.py").read_text() == "a = 1\nb = 9\nc = 3\n"


def test_replace_a_block_between_two_anchors(tmp_path):
    (tmp_path / "m.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
    ex = _ex(tmp_path)
    start, end = _anchor_of(ex, "m.py", "b"), _anchor_of(ex, "m.py", "c")
    r = ex.execute("edit_lines", {"path": "m.py", "at": start, "end": end, "new": "X\nY"})
    assert r.ok and (tmp_path / "m.py").read_text() == "a\nX\nY\nd\n"


def test_insert_after_a_line(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\nc = 3\n", encoding="utf-8")
    ex = _ex(tmp_path)
    after = _anchor_of(ex, "m.py", "a = 1")
    r = ex.execute("edit_lines", {"path": "m.py", "after": after, "new": "b = 2"})
    assert r.ok and (tmp_path / "m.py").read_text() == "a = 1\nb = 2\nc = 3\n"


def test_empty_new_deletes_the_anchored_line(tmp_path):
    (tmp_path / "m.py").write_text("a\nb\nc\n", encoding="utf-8")
    ex = _ex(tmp_path)
    at = _anchor_of(ex, "m.py", "b")
    r = ex.execute("edit_lines", {"path": "m.py", "at": at, "new": ""})
    assert r.ok and (tmp_path / "m.py").read_text() == "a\nc\n"


# --- fail-closed guarantees ----------------------------------------------

def test_unknown_anchor_is_refused_and_file_untouched(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\n", encoding="utf-8")
    ex = _ex(tmp_path)
    r = ex.execute("edit_lines", {"path": "m.py", "at": "deadbeef", "new": "a = 9"})
    assert not r.ok and "not found" in r.output
    assert (tmp_path / "m.py").read_text() == "a = 1\n"      # unchanged


def test_a_shifted_anchor_no_longer_matches(tmp_path):
    # Read anchors, delete an earlier line, then a later line's old anchor is stale:
    # its position changed, so the edit is refused rather than hitting the wrong line.
    (tmp_path / "m.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    ex = _ex(tmp_path)
    a_one, a_three = _anchor_of(ex, "m.py", "one"), _anchor_of(ex, "m.py", "three")
    ex.execute("edit_lines", {"path": "m.py", "at": a_one, "new": ""})   # drop line 1
    r = ex.execute("edit_lines", {"path": "m.py", "at": a_three, "new": "THREE"})
    assert not r.ok and "not found" in r.output
    assert (tmp_path / "m.py").read_text() == "two\nthree\n"      # untouched by the stale edit


def test_edit_lines_is_gated_like_write(tmp_path):
    (tmp_path / "m.py").write_text("k = 1\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = ex.execute("edit_lines", {"path": "m.py", "at": "abc", "new": "k = 2"})
    assert not r.ok and "[gate]" in r.output
    assert (tmp_path / "m.py").read_text() == "k = 1\n"          # unchanged


def test_edit_lines_needs_at_or_after(tmp_path):
    (tmp_path / "m.py").write_text("a\n", encoding="utf-8")
    r = _ex(tmp_path).execute("edit_lines", {"path": "m.py", "new": "b"})
    assert not r.ok and "needs 'at'" in r.output


# --- end-of-file newline fidelity ----------------------------------------

def test_insert_after_final_line_without_trailing_newline(tmp_path):
    (tmp_path / "m.py").write_text("only line", encoding="utf-8")   # no EOL
    ex = _ex(tmp_path)
    after = _anchor_of(ex, "m.py", "only line")
    r = ex.execute("edit_lines", {"path": "m.py", "after": after, "new": "added"})
    assert r.ok and (tmp_path / "m.py").read_text() == "only line\nadded\n"


def test_replace_final_line_preserves_missing_trailing_newline(tmp_path):
    (tmp_path / "m.py").write_text("a\nb", encoding="utf-8")        # b has no EOL
    ex = _ex(tmp_path)
    at = _anchor_of(ex, "m.py", "b")
    r = ex.execute("edit_lines", {"path": "m.py", "at": at, "new": "B"})
    assert r.ok and (tmp_path / "m.py").read_text() == "a\nB"       # still no trailing EOL


# --- the new path is covered by the same guards --------------------------

def test_edit_lines_is_in_the_canonical_write_set():
    assert "edit_lines" in WRITE_TOOLS


def test_editing_a_protected_test_file_via_edit_lines_is_flagged():
    led = _led(("edit_lines", '{"path": "tests/test_core.py", "at": "abc", "new": "pass"}'))
    flags = trajectory_integrity(led)
    assert any(f.kind == "edited_protected_file" for f in flags)


def test_reward_hacking_injected_via_edit_lines_is_flagged():
    led = _led(("edit_lines",
                '{"path": "app.py", "at": "abc", "new": "import pytest\\npytestmark = pytest.mark.skip"}'))
    flags = trajectory_integrity(led)
    assert any("skip" in f.kind for f in flags)
