"""The fresh-context reviewer: an independent second opinion over the diff only.

Load-bearing: the reviewer's prompt carries the task and the diff but NOT the
author's reasoning or receipts, so it cannot inherit the author's blind spots.
"""
from relay.local_review_agent import (
    APPROVE,
    REQUEST_CHANGES,
    UNCLEAR,
    parse_verdict,
    review_run,
    witnessed_diff,
)
from relay.local_session import SessionLedger


class _FakeAgent:
    def __init__(self, reply):
        self._reply = reply
        self.system = ""
        self.sent = None

    def send(self, text):
        self.sent = text
        return {"content": [{"text": self._reply}], "backend": "fake"}


def _run_ledger():
    led = SessionLedger()
    led.append("user", "fix the off-by-one in paginate()")
    led.append("assistant", "AUTHOR-PRIVATE-REASONING: I think the slice is wrong.")
    led.append("tool_call", 'edit_file {"path": "page.py", "old": "size-1", "new": "size"}')
    led.append("tool_result", "edited page.py", {"tool": "edit_file", "ok": True})
    led.append("assistant", "Done.", {"receipt": {"receipt_id": "abc"}})
    return led


def test_reviewer_sees_the_diff_and_task_but_not_the_author_reasoning():
    agent = _FakeAgent("REQUEST_CHANGES\n- off-by-one may now over-run by one")
    out = review_run(lambda: agent, _run_ledger())
    assert out["verdict"] == REQUEST_CHANGES and out["reviewed"] is True
    assert "paginate()" in agent.sent          # the task is shown
    assert "page.py" in agent.sent and "size" in agent.sent  # the diff is shown
    assert "AUTHOR-PRIVATE-REASONING" not in agent.sent      # the ledger is NOT shown
    assert "receipt" not in agent.sent


def test_approve_verdict_is_parsed():
    agent = _FakeAgent("APPROVE\n- looks correct")
    assert review_run(lambda: agent, _run_ledger())["verdict"] == APPROVE


def test_no_witnessed_edits_is_trivially_approved_not_reviewed():
    led = SessionLedger()
    led.append("user", "just answer a question")
    led.append("assistant", "The answer is 42.")
    out = review_run(lambda: _FakeAgent("REQUEST_CHANGES"), led)
    assert out["verdict"] == APPROVE and out["reviewed"] is False


def test_witnessed_diff_covers_write_and_edit_only():
    led = SessionLedger()
    led.append("tool_call", 'read_file {"path": "x.py"}')          # not an edit
    led.append("tool_call", 'write_file {"path": "a.py", "content": "hello"}')
    led.append("tool_call", 'edit_file {"path": "b.py", "old": "x", "new": "y"}')
    diff = witnessed_diff(led)
    assert "a.py (written)" in diff and "hello" in diff
    assert "b.py (edited)" in diff and "- x" in diff and "+ y" in diff
    assert "x.py" not in diff                                       # reads are not a diff


def test_parse_verdict_prefers_the_first_line_then_scans():
    assert parse_verdict("APPROVE\nrequest changes mentioned in prose") == APPROVE
    assert parse_verdict("Summary\n...\nREQUEST_CHANGES: missing test") == REQUEST_CHANGES
    assert parse_verdict("hmm, not sure") == UNCLEAR
