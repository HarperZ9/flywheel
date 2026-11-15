"""git-bisect for a witnessed agent run: localize the first edit that breaks the check.

The model is never re-run -- only the recorded edits are replayed against a
deterministic (here injected) check -- so the localization is offline and exact.
"""
from pathlib import Path

from relay.bisect import bisect_run, edit_set
from relay.local_session import SessionLedger


def _base(tmp_path, files: dict) -> str:
    root = tmp_path / "base"
    root.mkdir()
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return str(root)


def _led(*edits) -> SessionLedger:
    led = SessionLedger()
    led.append("user", "make the change")
    led.append("assistant", "editing now")
    for content in edits:
        led.append("tool_call", content)
    return led


def _reads(rel):
    def runner(check, root):
        text = (Path(root) / rel).read_text(encoding="utf-8")
        return ("BROKEN" not in text), text
    return runner


def test_first_bad_edit_is_the_one_that_introduces_the_break(tmp_path):
    base = _base(tmp_path, {"app.py": "def f():\n    return 1\n"})
    led = _led(
        'edit_file {"path": "app.py", "old": "return 1", "new": "return 2"}',       # seq 2, ok
        'edit_file {"path": "app.py", "old": "return 2", "new": "raise BROKEN()"}',  # seq 3, BAD
        'write_file {"path": "notes.txt", "content": "done"}',                        # seq 4, ok
    )
    out = bisect_run(led, base, "check", runner=_reads("app.py"))
    assert out["first_bad_seq"] == 3
    assert out["first_bad_edit"]["path"] == "app.py"
    assert out["edited_protected"] is False


def test_a_bad_edit_to_a_grader_file_is_flagged(tmp_path):
    base = _base(tmp_path, {"tests/test_x.py": "def test_x():\n    assert real()\n"})
    led = _led(
        'edit_file {"path": "tests/test_x.py", "old": "assert real()", "new": "assert BROKEN"}',
    )
    out = bisect_run(led, base, "check", runner=_reads("tests/test_x.py"))
    assert out["first_bad_seq"] == 2
    assert out["edited_protected"] is True  # it also touched the grader


def test_no_witnessed_edits_has_nothing_to_bisect(tmp_path):
    base = _base(tmp_path, {"app.py": "ok\n"})
    out = bisect_run(_led(), base, "check", runner=_reads("app.py"))
    assert out["first_bad_seq"] is None and "no witnessed edits" in out["note"]


def test_a_base_that_already_fails_is_reported_not_localized(tmp_path):
    base = _base(tmp_path, {"app.py": "raise BROKEN()\n"})  # fails before any edit
    led = _led('write_file {"path": "app.py", "content": "fixed"}')
    out = bisect_run(led, base, "check", runner=_reads("app.py"))
    assert out["first_bad_seq"] is None and "already fails" in out["note"]


def test_an_edit_set_that_still_passes_has_no_bad_edit(tmp_path):
    base = _base(tmp_path, {"app.py": "return 1\n"})
    led = _led('edit_file {"path": "app.py", "old": "return 1", "new": "return 2"}')
    out = bisect_run(led, base, "check", runner=_reads("app.py"))
    assert out["first_bad_seq"] is None and "still passes" in out["note"]


def test_edit_set_extraction_keeps_order_and_seq(tmp_path):
    led = _led('read_file {"path": "app.py"}' if False else
               'write_file {"path": "a.py", "content": "x"}',
               'edit_file {"path": "b.py", "old": "x", "new": "y"}')
    es = edit_set(led)
    assert [(name, args["path"]) for _, name, args in es] == [
        ("write_file", "a.py"), ("edit_file", "b.py")]
    assert [seq for seq, _, _ in es] == [2, 3]
