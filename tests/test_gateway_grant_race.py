import threading

import harness.gateway_grant_inbox as grant_inbox
from gateway_grant_relay_source_fixture import relay_source_runtime  # noqa: F401
from test_gateway_grant_inbox import (
    _approve_reviewed,
    _assert_approve_reject_race_terminal,
    _journey,
    _prepare,
    _read,
    _record_outcome,
    _reject,
)


def test_approve_reject_busy_loser_retries_as_terminal_conflict(
        tmp_path, monkeypatch):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    read, _ = _read(tmp_path, proposal)
    item = {"proposal_ref": proposal["proposal_ref"],
            "record_sha256": read["record_sha256"]}
    review = read["review"]
    issue_entered = threading.Event()
    release_issue = threading.Event()
    original_issue_exact = grant_inbox.GrantStore.issue_exact

    def delayed_issue_exact(self, *args, **kwargs):
        issue_entered.set()
        if not release_issue.wait(timeout=5.0):
            raise AssertionError("approval delay was not released")
        return original_issue_exact(self, *args, **kwargs)

    monkeypatch.setattr(
        grant_inbox.GrantStore, "issue_exact", delayed_issue_exact)
    outcomes = []
    errors = []
    approve = threading.Thread(target=_record_outcome, args=(
        outcomes, errors, "approve",
        lambda: _approve_reviewed(tmp_path, proposal, review)))
    reject = threading.Thread(target=_record_outcome, args=(
        outcomes, errors, "reject", lambda: _reject(tmp_path, item)))

    approve.start()
    assert issue_entered.wait(timeout=5.0)
    reject.start()
    try:
        reject.join(timeout=5.0)
        assert not reject.is_alive()
    finally:
        release_issue.set()
    approve.join(timeout=5.0)
    assert not approve.is_alive()

    _assert_approve_reject_race_terminal(
        tmp_path, proposal, review, item, outcomes, errors)
