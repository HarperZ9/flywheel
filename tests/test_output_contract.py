"""Falsifiers for the check an answer passes before anyone reads it.

The case these are written against is a published one. A frontier demo filled
out a Form 1040 and computed the tax from the rate schedule, which gives
$4,165.50, where the form requires the tax table, which gives $4,169. No amount
of rechecking the arithmetic finds that, because the arithmetic was right. What
was wrong was which source got to decide.

So the three outcomes each get a test, and the third is the one that matters
most: a correct value nobody traced back to the authority is unverified, not
passed.
"""
import pytest

from harness.contract_feedback import feedback
from harness.output_contract import (AUTHORITY_UNAVAILABLE, CITED, DISAGREES,
                                     FIELD_ABSENT, OUT_OF_RANGE, TABLE, UNCITED,
                                     ContractError, check_answer, new_contract)
from harness.verdict import Verdict
from tests.tax_authority_fixture import (SCHEDULE_ID, TABLE_ID, schedule,
                                         tax_table_authority)

CONTRACT = new_contract([{"name": "tax", "authority": TABLE, "source": TABLE_ID,
                          "describes": "Form 1040 line 16"}])
AUTHORITIES = {TABLE_ID: tax_table_authority}
FROM_THE_TABLE = 4169
FROM_THE_SCHEDULE = float(schedule(36700))


def answer(value, source=None, income=36700):
    fields = {"taxable_income": {"value": income, "source": "the return"},
              "tax": {"value": value}}
    if source is not None:
        fields["tax"]["source"] = source
    return fields


def only(report):
    assert len(report["fields"]) == 1
    return report["fields"][0]


def test_the_answer_the_published_demo_gave_fails_against_the_table():
    """$4,165.50 is what the rate schedule gives and what the demo wrote."""
    assert FROM_THE_SCHEDULE == 4165.50
    report = check_answer(answer(FROM_THE_SCHEDULE, TABLE_ID), CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.FAIL.value
    assert only(report)["code"] == DISAGREES
    assert report["unresolved"] == ["tax"]


def test_the_value_the_table_gives_passes():
    report = check_answer(answer(FROM_THE_TABLE, TABLE_ID), CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.PASS.value
    assert report["passed"] == report["checked"] == 1
    assert report["unresolved"] == []


def test_a_correct_value_nobody_traced_is_unverified_rather_than_passed():
    """The outcome that usually gets rounded away. Right this once is not the
    same as right, and a run that cannot say where a number came from cannot
    say it will hold on the next input."""
    report = check_answer(answer(FROM_THE_TABLE), CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == UNCITED
    assert only(report)["cited"] is False


def test_citing_the_wrong_source_does_not_count_as_citing():
    report = check_answer(answer(FROM_THE_TABLE, SCHEDULE_ID), CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == UNCITED


def test_a_field_the_answer_never_states_is_unverified_rather_than_failed():
    """Silence is not a wrong answer. Scoring it as one teaches a model that
    guessing beats declining, which is the opposite of the point."""
    report = check_answer({"taxable_income": {"value": 36700}}, CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == FIELD_ABSENT


def test_an_input_the_authority_does_not_cover_is_unverified_not_failed():
    report = check_answer(answer(9999, TABLE_ID, income=60000), CONTRACT, AUTHORITIES)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == OUT_OF_RANGE
    assert "48,475" in only(report)["reason"]


def test_an_authority_the_caller_never_supplied_is_unverified_not_passed():
    """A missing checker must never read as a clean check."""
    report = check_answer(answer(FROM_THE_TABLE, TABLE_ID), CONTRACT, {})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE


def test_no_report_ever_carries_the_value_the_authority_gave():
    """The report feeds the next attempt. An attempt that copies a number out
    of its own failure report has consulted nothing."""
    report = check_answer(answer(FROM_THE_SCHEDULE, TABLE_ID), CONTRACT, AUTHORITIES)
    assert "4169" not in repr(report)
    assert "4169" not in repr(feedback(report))


def test_feedback_names_the_authority_and_drops_what_already_passed():
    contract = new_contract([
        {"name": "tax", "authority": TABLE, "source": TABLE_ID},
        {"name": "method", "authority": CITED, "source": SCHEDULE_ID},
    ])
    stated = answer(FROM_THE_SCHEDULE, TABLE_ID)
    stated["method"] = {"value": "rate schedule", "source": SCHEDULE_ID}
    authorities = dict(AUTHORITIES)
    authorities[SCHEDULE_ID] = lambda _: None
    hint = feedback(check_answer(stated, contract, authorities))
    assert [row["field"] for row in hint["fields"]] == ["tax"]
    assert TABLE_ID in hint["fields"][0]["do"]


def test_a_citation_check_never_returns_fail():
    """It can only say whether the answer named the source. Deciding a value is
    wrong is not something a citation is able to do."""
    contract = new_contract([{"name": "method", "authority": CITED,
                              "source": SCHEDULE_ID}])
    for claim in ({"value": "anything at all", "source": SCHEDULE_ID},
                  {"value": "anything at all"},
                  {"value": None, "source": "somewhere else"}):
        report = check_answer({"method": claim}, contract,
                              {SCHEDULE_ID: lambda _: None})
        assert report["verdict"] != Verdict.FAIL.value


def test_the_worst_field_decides_the_run_and_not_the_majority():
    contract = new_contract([
        {"name": "tax", "authority": TABLE, "source": TABLE_ID},
        {"name": "method", "authority": CITED, "source": SCHEDULE_ID},
    ])
    stated = answer(FROM_THE_SCHEDULE, TABLE_ID)
    stated["method"] = {"value": "rate schedule", "source": SCHEDULE_ID}
    authorities = dict(AUTHORITIES)
    authorities[SCHEDULE_ID] = lambda _: None
    report = check_answer(stated, contract, authorities)
    assert report["passed"] == 1 and report["checked"] == 2
    assert report["verdict"] == Verdict.FAIL.value


def test_true_does_not_agree_with_a_tax_of_one_dollar():
    """A bool is an int in Python, so this is a real way to pass by accident."""
    contract = new_contract([{"name": "tax", "authority": TABLE, "source": "flat"}])
    report = check_answer({"tax": {"value": True, "source": "flat"}},
                          contract, {"flat": lambda _: 1})
    assert report["verdict"] == Verdict.FAIL.value


def test_a_tolerance_is_zero_unless_the_contract_asks_for_one():
    """Money is exact. A default tolerance would have passed the demo answer."""
    assert CONTRACT[0]["tolerance"] == 0.0
    loose = new_contract([{"name": "tax", "authority": TABLE, "source": TABLE_ID,
                           "tolerance": 5}])
    report = check_answer(answer(FROM_THE_SCHEDULE, TABLE_ID), loose, AUTHORITIES)
    assert report["verdict"] == Verdict.PASS.value


def test_checking_an_answer_does_not_change_it():
    stated = answer(FROM_THE_SCHEDULE, TABLE_ID)
    before = repr(stated)
    check_answer(stated, CONTRACT, AUTHORITIES)
    assert repr(stated) == before


def test_a_contract_that_requires_nothing_is_refused():
    with pytest.raises(ContractError, match="accepts everything"):
        new_contract([])


def test_a_malformed_contract_is_refused_at_construction():
    for spec, match in (
        ({"name": "tax", "authority": TABLE}, "missing source"),
        ({"name": "tax", "authority": "VIBES", "source": TABLE_ID}, "unknown authority"),
    ):
        with pytest.raises(ContractError, match=match):
            new_contract([spec])
    with pytest.raises(ContractError, match="duplicate field"):
        new_contract([{"name": "tax", "authority": TABLE, "source": TABLE_ID}] * 2)
