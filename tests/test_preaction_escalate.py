"""Hold and escalate (bank B7): the call never runs unless an unexpired one-use
grant matches its exact arguments digest.

Success criteria: the sealed hold record exists before the outcome returns; a
record-write failure blocks; approval admits exactly one identical call;
changed arguments get a new hold; reject, terminate and expiry never run the
call; an unavailable escalation store blocks; an interactive approver must see
the review payload and type the confirmation code.
"""
from __future__ import annotations

import json

import pytest

from harness.preaction import records
from harness.preaction.contract import BLOCK, HOLD
from harness.preaction.escalate import TtyApprover, review_payload
from tests.preaction_fixtures import Clock, call, ctx, monitor

PUSH = dict(cmd="git push --force origin main")


def _records(home):
    return records.HoldStore(home).read_all()


def test_hold_writes_sealed_record_before_returning(tmp_path):
    mon = monitor(tmp_path)
    out = mon.gate(call("run", **PUSH), ctx())
    assert out.verdict == HOLD and not out.run
    recs = _records(tmp_path)
    assert recs[-1]["schema"] == records.HOLD_SCHEMA
    assert recs[-1]["seal"]["hex"] == out.assessment.record_sha256
    assert records.verify_seal(recs[-1])
    assert "intent" in recs[-1]["does_not_prove"]
    assert "git push" not in json.dumps(recs[-1])  # digests only, never raw arguments


def test_record_write_failure_blocks(tmp_path, monkeypatch):
    mon = monitor(tmp_path)

    def boom(*a, **k):
        raise records.RecordWriteError("disk full")
    monkeypatch.setattr(mon.store, "append", boom)
    out = mon.gate(call("run", **PUSH), ctx())
    assert out.verdict == BLOCK and not out.run
    assert "record_write_failed" in {r["id"] for r in out.assessment.reasons}


def test_escalation_unavailable_blocks(tmp_path, monkeypatch):
    mon = monitor(tmp_path)
    monkeypatch.setattr(mon.escalator, "file", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    out = mon.gate(call("run", **PUSH), ctx())
    assert out.verdict == BLOCK and "escalation_unavailable" in {r["id"] for r in out.assessment.reasons}


def test_approve_once_admits_exactly_one_identical_call(tmp_path):
    mon = monitor(tmp_path)
    c = ctx()
    held = mon.gate(call("run", **PUSH), c)
    assert [p["hold_id"] for p in mon.escalator.pending()] == [held.hold_id]
    mon.escalator.decide(held.hold_id, "APPROVED_ONCE", decider="owner")
    first = mon.gate(call("run", **PUSH), c)
    assert first.run and first.redeemed_hold_id == held.hold_id
    second = mon.gate(call("run", **PUSH), c)
    assert not second.run and second.verdict == HOLD


def test_changed_arguments_after_approval_get_a_new_hold(tmp_path):
    mon = monitor(tmp_path)
    c = ctx()
    held = mon.gate(call("run", **PUSH), c)
    mon.escalator.decide(held.hold_id, "APPROVED_ONCE", decider="owner")
    other = mon.gate(call("run", cmd="git push --force origin release"), c)
    assert not other.run and other.hold_id != held.hold_id


def test_grant_from_another_run_does_not_redeem(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx(run_id="a"))
    mon.escalator.decide(held.hold_id, "APPROVED_ONCE", decider="owner")
    assert not mon.gate(call("run", **PUSH), ctx(run_id="b")).run


@pytest.mark.parametrize("decision", ["REJECTED", "TERMINATED"])
def test_reject_and_terminate_never_run(tmp_path, decision):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx())
    mon.escalator.decide(held.hold_id, decision, decider="owner")
    assert not mon.gate(call("run", **PUSH), ctx()).run
    assert mon.escalator.pending() == []


def test_terminate_ends_the_run(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx())
    mon.escalator.decide(held.hold_id, "TERMINATED", decider="owner")
    nxt = mon.gate(call("read_file", path="src/a.py"), ctx())
    assert not nxt.run and "run-terminated" in {r["family"] for r in nxt.assessment.reasons}


def test_expiry_is_a_decision_and_never_yes(tmp_path):
    clock = Clock()
    mon = monitor(tmp_path, clock=clock)
    held = mon.gate(call("run", **PUSH), ctx())
    clock.advance(31 * 60)
    assert mon.escalator.expire_due() == [held.hold_id]
    decisions = [r for r in _records(tmp_path) if r["schema"] == records.DECISION_SCHEMA]
    assert decisions[-1]["decision"] == "EXPIRED"
    with pytest.raises(ValueError):
        mon.escalator.decide(held.hold_id, "APPROVED_ONCE", decider="owner")


def test_approved_grant_expires_unused(tmp_path):
    clock = Clock()
    mon = monitor(tmp_path, clock=clock)
    held = mon.gate(call("run", **PUSH), ctx())
    mon.escalator.decide(held.hold_id, "APPROVED_ONCE", decider="owner")
    clock.advance(301)
    assert not mon.gate(call("run", **PUSH), ctx()).run


def test_decision_record_chains_to_hold_and_binds_review_digest(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx())
    mon.escalator.decide(held.hold_id, "REJECTED", decider="owner")
    hold, decision = _records(tmp_path)[-2:]
    assert decision["hold_record_sha256"] == hold["seal"]["hex"]
    assert decision["prev_record_sha256"] == hold["seal"]["hex"]
    assert len(decision["review_payload_sha256"]) == 64


def test_review_payload_order_and_does_not_prove(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx(goal="update docs"))
    payload = review_payload(mon.escalator.read_pending(held.hold_id))
    assert list(payload)[:6] == ["proposed_action", "reasons", "goal_and_trajectory",
                                 "coverage", "does_not_prove", "expiry_and_owner"]
    assert payload["proposed_action"]["args"] == PUSH
    assert "intent" in payload["does_not_prove"]


def test_agent_text_is_neutral_and_omits_judge_justification(tmp_path):
    mon = monitor(tmp_path)
    out = mon.gate(call("run", **PUSH), ctx())
    assert out.agent_text.startswith("held for owner review (hold_id=")
    assert "force" not in out.agent_text


def test_inline_approver_decides_before_return(tmp_path):
    seen = []

    def approver(payload):
        seen.append(payload)
        return "APPROVED_ONCE"
    mon = monitor(tmp_path, approver=approver)
    out = mon.gate(call("run", **PUSH), ctx())
    assert out.run and seen and seen[0]["proposed_action"]["tool"] == "run"


def test_tty_approver_requires_the_typed_code():
    lines = iter(["a", "wrong-code"])
    out = []
    appr = TtyApprover(read=lambda prompt: next(lines), write=out.append, isatty=lambda: True)
    assert appr({"proposed_action": {"tool": "run", "args": {}}, "confirm_code": "ab12cd",
                 "reasons": [], "does_not_prove": "x"}) is None


def test_tty_approver_refuses_without_a_terminal():
    appr = TtyApprover(read=lambda p: "a", write=lambda s: None, isatty=lambda: False)
    assert appr({"confirm_code": "x"}) is None


def test_tty_approver_approves_with_code():
    lines = iter(["a", "ab12cd"])
    appr = TtyApprover(read=lambda prompt: next(lines), write=lambda s: None, isatty=lambda: True)
    assert appr({"proposed_action": {"tool": "run", "args": {}}, "confirm_code": "ab12cd",
                 "reasons": [], "does_not_prove": "x"}) == "APPROVED_ONCE"
