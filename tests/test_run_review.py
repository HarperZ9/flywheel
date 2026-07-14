"""The run review projects a witnessed ledger into what a senior reviewer
checks first — did it read before it cut, did an oracle cover the edits,
where did it stumble — from ledger facts ONLY. Every signal is named in
the payload and the score is re-derivable arithmetic, never a vibe."""

import json

from harness.run_review import SCHEMA, run_review


def _e(kind, content, meta=None):
    return {"kind": kind, "content": content, "meta": meta or {}}


def _call(name, args):
    return _e("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")


def _res(name, ok, output="ok"):
    return _e("tool_result", output, {"tool": name, "ok": ok})


def test_clean_run_reviews_clean():
    entries = [
        _e("user", "fix the bug"),
        _call("read_file", {"path": "a.py"}),
        _res("read_file", True),
        _call("edit_file", {"path": "a.py", "old": "x", "new": "y"}),
        _res("edit_file", True),
        _call("run", {"cmd": "pytest -q"}),
        _res("run", True),
    ]
    doc = run_review(entries)
    assert doc["schema"] == SCHEMA
    assert doc["edited_unread"] == []
    assert doc["unverified_edits"] == []
    assert doc["failed_calls"] == 0
    assert doc["reviewability"] == 1.0
    assert "signals" in doc


def test_blind_edit_without_oracle_is_flagged():
    entries = [
        _e("user", "fix"),
        _call("write_file", {"path": "b.py", "content": "..."}),
        _res("write_file", True),
    ]
    doc = run_review(entries)
    assert doc["edited_unread"] == ["b.py"]
    assert doc["unverified_edits"] == ["b.py"]
    assert doc["reviewability"] < 0.5
    assert doc["signals"]["read_before_write_ratio"] == 0.0


def test_failures_are_retry_scars_not_hidden():
    entries = [
        _e("user", "fix"),
        _call("read_file", {"path": "a.py"}),
        _res("read_file", False, "no such file"),
        _call("read_file", {"path": "src/a.py"}),
        _res("read_file", True),
        _call("edit_file", {"path": "src/a.py", "old": "x", "new": "y"}),
        _res("edit_file", True),
        _call("run", {"cmd": "pytest"}),
        _res("run", False, "1 failed"),
        _call("edit_file", {"path": "src/a.py", "old": "y", "new": "z"}),
        _res("edit_file", True),
        _call("run", {"cmd": "pytest"}),
        _res("run", True),
    ]
    doc = run_review(entries)
    assert doc["failed_calls"] == 2
    assert doc["edited_unread"] == []
    assert doc["unverified_edits"] == []
    assert 0.0 < doc["reviewability"] <= 1.0


def test_gate_denials_are_policy_receipts_not_noise():
    """Import 1 from the landscape queue: every allow/deny is journaled.
    A gate denial is a policy event with the rule visible, distinct from
    an ordinary failed call."""
    entries = [
        _e("user", "fix"),
        _call("write_file", {"path": "a.py", "content": "x"}),
        _res("write_file", False,
             "[gate] write is disabled (pass --allow-write)"),
    ]
    doc = run_review(entries)
    assert doc["gate_denials"] == [{
        "tool": "write_file",
        "rule": "[gate] write is disabled (pass --allow-write)",
    }]
    # A denial is a policy verdict, not a model stumble.
    assert doc["failed_calls"] == 0


def test_edits_after_the_last_green_run_are_unverified():
    entries = [
        _e("user", "fix"),
        _call("read_file", {"path": "a.py"}),
        _res("read_file", True),
        _call("run", {"cmd": "pytest"}),
        _res("run", True),
        _call("edit_file", {"path": "a.py", "old": "x", "new": "y"}),
        _res("edit_file", True),
    ]
    doc = run_review(entries)
    assert doc["unverified_edits"] == ["a.py"]
