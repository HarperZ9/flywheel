"""Typed override reasons and the later outcome check.

Success criteria: a reason code from the fixed list lands in the sealed decision
record and an unknown code is refused before anything is written; the free text
stays in an owner-only side file and the record keeps only its digest; a decision
with no code keeps the old record shape; an outcome links to its decision, takes
its verdict from typed evidence that must fit the decision, is refused twice and
is marked self_check when the decider checks it; the store still verifies.
"""
from __future__ import annotations

import json

import pytest

from harness.preaction import records
from harness.preaction.contract import sha256_hex
from harness.preaction.overrides import (OUTCOME_SCHEMA, read_reason_text, record_outcome)
from harness.preaction.verify import verify_store
from tests.preaction_fixtures import Clock, call, ctx, monitor

PUSH = dict(cmd="git push --force origin main")


def _decided(home, decision="APPROVED_ONCE", **kw):
    mon = monitor(home)
    held = mon.gate(call("run", **PUSH), ctx())
    mon.escalator.decide(held.hold_id, decision, decider="owner", **kw)
    return records.HoldStore(home).read_all()[-1]


def test_reason_code_is_sealed_in_the_decision(tmp_path):
    dec = _decided(tmp_path, reason_code="rule_false_positive", reason="tests need the push")
    assert dec["reason_code"] == "rule_false_positive" and records.verify_seal(dec)
    assert dec["reason_sha256"] == sha256_hex(b"tests need the push")


def test_free_text_stays_owner_only_beside_the_digest(tmp_path):
    dec = _decided(tmp_path, reason_code="needs_more_context", reason="asked the author first")
    assert "asked the author" not in json.dumps(dec)
    assert read_reason_text(tmp_path, dec["seal"]["hex"]) == "asked the author first"


def test_unknown_code_is_refused_and_nothing_is_written(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", **PUSH), ctx())
    before = len(records.HoldStore(tmp_path).read_all())
    with pytest.raises(ValueError):
        mon.escalator.decide(held.hold_id, "REJECTED", decider="owner", reason_code="because")
    assert len(records.HoldStore(tmp_path).read_all()) == before
    assert [p["hold_id"] for p in mon.escalator.pending()] == [held.hold_id]


def test_uncoded_decision_keeps_the_old_shape(tmp_path):
    assert "reason_code" not in _decided(tmp_path, decision="REJECTED")


@pytest.mark.parametrize("decision,evidence,verdict", [
    ("APPROVED_ONCE", "no_harm_observed", "RIGHT"), ("APPROVED_ONCE", "harm_observed", "WRONG"),
    ("REJECTED", "call_not_needed", "RIGHT"), ("REJECTED", "call_was_needed", "WRONG"),
    ("REJECTED", "not_determinable", "UNKNOWN")])
def test_outcome_verdict_follows_typed_evidence(tmp_path, decision, evidence, verdict):
    dec = _decided(tmp_path, decision=decision, reason_code="wrong_target")
    rec = record_outcome(tmp_path, Clock(), dec["seal"]["hex"], evidence, checked_by="reviewer")
    stored = records.HoldStore(tmp_path).read_all()[-1]
    assert stored["schema"] == OUTCOME_SCHEMA and stored["verdict_on_decision"] == verdict
    assert stored["decision_record_sha256"] == dec["seal"]["hex"] == rec["decision_record_sha256"]
    assert stored["reason_code"] == "wrong_target" and stored["self_check"] is False


def test_evidence_must_fit_the_decision(tmp_path):
    dec = _decided(tmp_path, decision="APPROVED_ONCE")
    with pytest.raises(ValueError):
        record_outcome(tmp_path, Clock(), dec["seal"]["hex"], "call_was_needed", checked_by="r")


def test_expiry_takes_no_outcome(tmp_path):
    clock = Clock()
    mon = monitor(tmp_path, clock=clock)
    mon.gate(call("run", **PUSH), ctx())
    clock.advance(31 * 60)
    mon.escalator.expire_due()
    dec = records.HoldStore(tmp_path).read_all()[-1]
    with pytest.raises(ValueError):
        record_outcome(tmp_path, clock, dec["seal"]["hex"], "not_determinable", checked_by="r")


def test_second_outcome_is_refused_and_self_check_is_marked(tmp_path):
    dec = _decided(tmp_path)
    rec = record_outcome(tmp_path, Clock(), dec["seal"]["hex"], "no_harm_observed",
                         checked_by="owner", note="ran clean")
    assert rec["self_check"] is True and rec["note_sha256"] == sha256_hex(b"ran clean")
    with pytest.raises(ValueError):
        record_outcome(tmp_path, Clock(), dec["seal"]["hex"], "harm_observed", checked_by="r")


def test_outcome_needs_a_real_decision_and_a_checker(tmp_path):
    dec = _decided(tmp_path)
    with pytest.raises(ValueError):
        record_outcome(tmp_path, Clock(), "0" * 64, "no_harm_observed", checked_by="r")
    with pytest.raises(ValueError):
        record_outcome(tmp_path, Clock(), dec["seal"]["hex"], "no_harm_observed", checked_by="")


def test_store_with_codes_and_outcomes_still_verifies(tmp_path):
    dec = _decided(tmp_path, reason_code="scope_exceeded", reason="x")
    record_outcome(tmp_path, Clock(), dec["seal"]["hex"], "no_harm_observed", checked_by="r")
    assert verify_store(tmp_path)["verdict"] != "DRIFT"
