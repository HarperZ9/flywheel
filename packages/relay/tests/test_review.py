"""The reviewability projection: turn a witnessed run into the terms a senior
reviewer checks first (what was edited unread, what no check verified, the retry
scars, and per-edit risk tiers) -- facts from the ledger only, re-derivable."""

import json

from relay.local_session import SessionLedger
from relay.review import risk_review, run_review


def _call(led, name, args):
    led.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")


def _result(led, tool, ok, content=""):
    led.append("tool_result", content, {"tool": tool, "ok": ok})


def test_edited_unread_flags_a_write_with_no_prior_read():
    led = SessionLedger()
    _call(led, "write_file", {"path": "app.py", "content": "x = 1\n"})
    _result(led, "write_file", True)
    rv = run_review(led.entries)
    assert rv["edited_unread"] == ["app.py"]
    assert rv["signals"]["read_before_write_ratio"] == 0.0


def test_read_before_write_is_clean():
    led = SessionLedger()
    _call(led, "read_file", {"path": "app.py"})
    _result(led, "read_file", True, "old")
    _call(led, "edit_file", {"path": "app.py", "old": "a", "new": "b"})
    _result(led, "edit_file", True)
    rv = run_review(led.entries)
    assert rv["edited_unread"] == []
    assert rv["signals"]["read_before_write_ratio"] == 1.0


def test_a_passing_check_verifies_the_edits_and_a_missing_one_does_not():
    def build(with_pass):
        led = SessionLedger()
        _call(led, "write_file", {"path": "app.py", "content": "x = 1\n"})
        _result(led, "write_file", True)
        if with_pass is not None:
            led.append("check", "[exit 0]", {"cmd": "pytest -q", "ok": with_pass})
        return run_review(led.entries)
    assert build(True)["unverified_edits"] == []          # a green check verifies the edit
    assert build(False)["unverified_edits"] == ["app.py"]  # a failed check does not
    assert build(None)["unverified_edits"] == ["app.py"]   # no check -> unverified


def test_failed_calls_are_kept_visible():
    led = SessionLedger()
    _call(led, "edit_file", {"path": "a.py", "old": "zzz", "new": "q"})
    _result(led, "edit_file", False, "[error] not found")
    rv = run_review(led.entries)
    assert rv["failed_calls"] == 1
    assert 0.0 <= rv["reviewability"] <= 1.0


def test_gate_denials_are_receipts_not_stumbles():
    led = SessionLedger()
    _call(led, "write_file", {"path": "a.py", "content": "x"})
    _result(led, "write_file", False, "[gate] write disabled (pass --allow-write)")
    rv = run_review(led.entries)
    assert rv["failed_calls"] == 0                         # a policy denial is not a stumble
    assert rv["gate_denials"] and rv["gate_denials"][0]["tool"] == "write_file"


def test_risk_review_tiers_a_big_nested_edit_high_and_a_tiny_one_low():
    led = SessionLedger()
    big = "def f(x):\n" + "".join(
        f"    if x == {i}:\n        for j in range(x):\n            y = j\n" for i in range(20))
    _call(led, "write_file", {"path": "big.py", "content": big})
    _call(led, "edit_file", {"path": "small.py", "old": "a", "new": "b = 2\n"})
    rr = risk_review(led.entries)
    rows = {e["path"]: e for e in rr["edits"]}
    assert rows["big.py"]["tier"] == "high" and rows["big.py"]["lines_added"] > 50
    assert rows["small.py"]["tier"] == "low"
    assert [d["path"] for d in rr["demands"]] == ["big.py"]   # high tier demands a receipt
