"""Falsifiers for the loop that checks an answer before anyone reads it.

The producers here are deliberate. A model that rechecks its own arithmetic
reproduces its own wrong number, so a retry only means something when the
feedback sends it somewhere it has not already been. These fake producers make
that observable: one goes and looks, one does not, and the loop is expected to
tell them apart.
"""
import pytest

from harness.output_contract import TABLE, new_contract
from harness.validated_answer import (ATTEMPTS_EXHAUSTED, NO_PROGRESS,
                                      VALIDATED, ValidationError, emission,
                                      run_validated)
from harness.verdict import Verdict
from tests.tax_authority_fixture import TABLE_ID, schedule, tax_table_authority

CONTRACT = new_contract([{"name": "tax", "authority": TABLE, "source": TABLE_ID}])
AUTHORITIES = {TABLE_ID: tax_table_authority}
FROM_THE_TABLE = 4169
FROM_THE_SCHEDULE = float(schedule(36700))


def stated(value):
    return {"taxable_income": {"value": 36700, "source": "the return"},
            "tax": {"value": value, "source": TABLE_ID}}


def producer(*values):
    """Answers in order, recording the feedback each attempt was handed."""
    seen = []

    def produce(hint):
        seen.append(hint)
        return stated(values[min(len(seen) - 1, len(values) - 1)])

    produce.seen = seen
    return produce


def test_an_attempt_that_goes_and_looks_is_emitted():
    """The whole point. The first answer is the published demo's, the second is
    what the table says, and only the second gets out."""
    produce = producer(FROM_THE_SCHEDULE, FROM_THE_TABLE)
    result = run_validated(produce, CONTRACT, AUTHORITIES)
    assert result["verdict"] == Verdict.PASS.value
    assert result["halted"] == VALIDATED
    assert result["emit"] is True
    assert result["attempts"] == 2


def test_the_first_attempt_is_handed_no_feedback():
    produce = producer(FROM_THE_TABLE)
    run_validated(produce, CONTRACT, AUTHORITIES)
    assert produce.seen == [None]


def test_the_feedback_reaching_the_next_attempt_names_the_authority():
    produce = producer(FROM_THE_SCHEDULE, FROM_THE_TABLE)
    run_validated(produce, CONTRACT, AUTHORITIES)
    hint = produce.seen[1]
    assert hint["fields"][0]["field"] == "tax"
    assert TABLE_ID in hint["fields"][0]["do"]


def test_the_feedback_never_hands_over_the_value_that_would_pass():
    """A retry that copies a number out of its own failure report has consulted
    nothing, and would pass this loop while learning the opposite lesson."""
    produce = producer(FROM_THE_SCHEDULE, FROM_THE_TABLE)
    run_validated(produce, CONTRACT, AUTHORITIES)
    assert "4169" not in repr(produce.seen[1])


def test_the_same_mistake_twice_stops_the_loop():
    """A reroll is not a retry. Three more provider calls buy a costlier way to
    be wrong, so the loop stops the moment it lands somewhere it has been."""
    produce = producer(FROM_THE_SCHEDULE)
    result = run_validated(produce, CONTRACT, AUTHORITIES, max_attempts=5)
    assert result["halted"] == NO_PROGRESS
    assert result["attempts"] == 2


def test_two_wrong_shapes_alternating_are_caught_too():
    """Signatures are held as a set, so A to B and back to A is no progress
    even though no two consecutive attempts matched."""
    answers = [stated(FROM_THE_SCHEDULE),
               {"taxable_income": {"value": 36700}},
               stated(FROM_THE_SCHEDULE)]
    calls = []

    def produce(hint):
        calls.append(hint)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    result = run_validated(produce, CONTRACT, AUTHORITIES, max_attempts=6)
    assert result["halted"] == NO_PROGRESS
    assert result["attempts"] == 3


def test_attempts_can_run_out_without_a_repeat():
    """Each attempt fails a different way, so nothing repeats and the ceiling is
    what stops it."""
    answers = [stated(FROM_THE_SCHEDULE),
               {"taxable_income": {"value": 36700}},
               {"tax": {"value": FROM_THE_TABLE}}]
    calls = []

    def produce(hint):
        calls.append(hint)
        return answers[len(calls) - 1]

    result = run_validated(produce, CONTRACT, AUTHORITIES, max_attempts=3)
    assert result["halted"] == ATTEMPTS_EXHAUSTED
    assert result["attempts"] == 3
    assert result["emit"] is False


def test_an_answer_that_never_validates_is_returned_with_the_reason():
    """Dropping it hides the work. Emitting it clean is the failure this module
    exists for: a wrong answer that arrived looking finished."""
    result = run_validated(producer(FROM_THE_SCHEDULE), CONTRACT, AUTHORITIES)
    out = emission(result)
    assert out["answer"]["tax"]["value"] == FROM_THE_SCHEDULE
    assert out["verdict"] == Verdict.FAIL.value
    assert out["unresolved"] == ["tax"]
    assert "draft" in out["notice"]


def test_a_validated_answer_travels_without_a_notice():
    result = run_validated(producer(FROM_THE_TABLE), CONTRACT, AUTHORITIES)
    out = emission(result)
    assert out["notice"] == ""
    assert out["unresolved"] == []


def test_an_unchecked_answer_says_so_rather_than_reading_as_wrong():
    """No authority was supplied, so the value is unverified. The notice has to
    carry that distinction or a reader treats a gap as a defect."""
    result = run_validated(producer(FROM_THE_TABLE), CONTRACT, {})
    out = emission(result)
    assert out["verdict"] == Verdict.UNVERIFIABLE.value
    assert "unchecked rather than wrong" in out["notice"]


def test_every_attempt_keeps_its_own_report():
    result = run_validated(producer(FROM_THE_SCHEDULE, FROM_THE_TABLE),
                           CONTRACT, AUTHORITIES)
    assert len(result["reports"]) == result["attempts"] == 2
    assert result["reports"][0]["verdict"] == Verdict.FAIL.value
    assert result["reports"][1]["verdict"] == Verdict.PASS.value


def test_a_loop_that_never_produces_an_answer_is_refused():
    with pytest.raises(ValidationError, match="cannot validate"):
        run_validated(producer(FROM_THE_TABLE), CONTRACT, AUTHORITIES,
                      max_attempts=0)
