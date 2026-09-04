"""Falsifiers for the authorities a value comparison cannot express.

The first version of the contract had three authority kinds and one verdict
axis, and it could not see any of these: a dose stated in the wrong unit, a
dose above a ceiling, a number reached by an equation the protocol forbids, or
a field whose failure should stop the answer leaving the building.
"""
import pytest

from harness.output_contract import (BOUND, CITED, CRITICAL, HOLD,
                                     METHOD_MISMATCH, METHOD_UNSTATED,
                                     OUT_OF_BOUND, RECOMPUTE, RELEASE,
                                     RELEASE_WITH_CAVEAT, TABLE, UNIT,
                                     UNIT_MISMATCH, UNIT_UNSTATED,
                                     ContractError, check_answer,
                                     new_contract, release_decision)
from harness.verdict import Verdict


def _spec(**over):
    spec = {"name": "dose", "authority": RECOMPUTE, "source": "protocol"}
    spec.update(over)
    return spec


def _claim(**over):
    claim = {"value": 500.0, "source": "protocol"}
    claim.update(over)
    return claim


# --- the unit authority ----------------------------------------------------

def test_a_dose_in_micrograms_where_milligrams_are_mandated_fails():
    contract = new_contract([_spec(authority=UNIT)])
    report = check_answer({"dose": _claim(unit="mcg")}, contract,
                          {"protocol": lambda _a: "mg"})
    assert report["verdict"] == Verdict.FAIL.value
    assert report["fields"][0]["code"] == UNIT_MISMATCH


def test_a_dose_that_states_no_unit_at_all_is_unverifiable():
    contract = new_contract([_spec(authority=UNIT)])
    report = check_answer({"dose": _claim()}, contract,
                          {"protocol": lambda _a: "mg"})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["fields"][0]["code"] == UNIT_UNSTATED


def test_the_mandated_unit_passes():
    contract = new_contract([_spec(authority=UNIT)])
    report = check_answer({"dose": _claim(unit="mg")}, contract,
                          {"protocol": lambda _a: "mg"})
    assert report["verdict"] == Verdict.PASS.value


# --- the bound authority ---------------------------------------------------

def test_an_arithmetically_perfect_value_above_the_ceiling_fails():
    contract = new_contract([_spec(authority=BOUND)])
    report = check_answer({"dose": _claim(value=4000.0)}, contract,
                          {"protocol": lambda _a: (False, "the daily maximum is 3000 mg")})
    assert report["verdict"] == Verdict.FAIL.value
    row = report["fields"][0]
    assert row["code"] == OUT_OF_BOUND
    assert "3000" in row["reason"]


def test_a_bare_false_from_a_bound_authority_still_fails():
    contract = new_contract([_spec(authority=BOUND)])
    report = check_answer({"dose": _claim()}, contract,
                          {"protocol": lambda _a: False})
    assert report["verdict"] == Verdict.FAIL.value
    assert report["fields"][0]["code"] == OUT_OF_BOUND


def test_a_permitted_value_passes_and_the_report_carries_the_reason():
    contract = new_contract([_spec(authority=BOUND)])
    report = check_answer({"dose": _claim()}, contract,
                          {"protocol": lambda _a: (True, "inside the ceiling")})
    assert report["verdict"] == Verdict.PASS.value
    assert report["fields"][0]["reason"] == "inside the ceiling"


def test_a_bound_row_never_carries_the_ceiling_as_a_value():
    """Feedback must not hand the next attempt the number it failed against."""
    contract = new_contract([_spec(authority=BOUND)])
    report = check_answer({"dose": _claim(value=4000.0)}, contract,
                          {"protocol": lambda _a: (False, "over")})
    assert "value" not in report["fields"][0]


# --- the method mandate ----------------------------------------------------

def test_the_right_number_by_the_forbidden_method_fails():
    """The whole point. Both equations return 62.0 here and one is forbidden."""
    contract = new_contract([_spec(name="egfr", method="ckd-epi-2021")])
    answer = {"egfr": {"value": 62.0, "source": "protocol",
                       "method": "cockcroft-gault"}}
    report = check_answer(answer, contract, {"protocol": lambda _a: 62.0})
    assert report["verdict"] == Verdict.FAIL.value
    row = report["fields"][0]
    assert row["code"] == METHOD_MISMATCH
    assert "cockcroft-gault" in row["reason"]
    assert "ckd-epi-2021" in row["reason"]


def test_an_answer_that_names_no_method_where_one_is_mandated_is_unverifiable():
    contract = new_contract([_spec(name="egfr", method="ckd-epi-2021")])
    answer = {"egfr": {"value": 62.0, "source": "protocol"}}
    report = check_answer(answer, contract, {"protocol": lambda _a: 62.0})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["fields"][0]["code"] == METHOD_UNSTATED


def test_the_method_is_checked_before_the_value():
    """A wrong method and a wrong value report the method, not the value."""
    contract = new_contract([_spec(name="egfr", method="ckd-epi-2021")])
    answer = {"egfr": {"value": 9.0, "source": "protocol",
                       "method": "mdrd"}}
    report = check_answer(answer, contract, {"protocol": lambda _a: 62.0})
    assert report["fields"][0]["code"] == METHOD_MISMATCH


def test_a_field_with_no_mandate_ignores_a_stated_method():
    contract = new_contract([_spec()])
    answer = {"dose": _claim(method="whatever-it-felt-like")}
    report = check_answer(answer, contract, {"protocol": lambda _a: 500.0})
    assert report["verdict"] == Verdict.PASS.value


def test_a_cited_field_still_has_to_satisfy_its_method_mandate():
    contract = new_contract([_spec(name="basis", authority=CITED,
                                   method="court-days")])
    answer = {"basis": {"value": "Rule 6", "source": "protocol",
                        "method": "calendar-days"}}
    report = check_answer(answer, contract, {"protocol": lambda _a: None})
    assert report["fields"][0]["code"] == METHOD_MISMATCH


# --- criticality and the release decision ----------------------------------

def test_criticality_never_softens_a_verdict():
    contract = new_contract([_spec(criticality="advisory")])
    report = check_answer({"dose": _claim(value=1.0)}, contract,
                          {"protocol": lambda _a: 500.0})
    assert report["verdict"] == Verdict.FAIL.value


def test_an_unverifiable_critical_field_holds_the_answer():
    contract = new_contract([_spec(criticality=CRITICAL)])
    report = check_answer({"dose": _claim()}, contract, {})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["release"] == HOLD
    assert report["blocking"] == ["dose"]


def test_an_unverifiable_standard_field_releases_with_a_caveat():
    contract = new_contract([_spec()])
    report = check_answer({"dose": _claim(source="somewhere-else")}, contract,
                          {"protocol": lambda _a: 500.0})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["release"] == RELEASE_WITH_CAVEAT
    assert report["blocking"] == []


def test_a_clean_report_releases():
    contract = new_contract([_spec()])
    report = check_answer({"dose": _claim()}, contract,
                          {"protocol": lambda _a: 500.0})
    assert report["release"] == RELEASE


def test_a_fail_holds_whatever_the_criticality_says():
    rows = [{"field": "a", "verdict": Verdict.FAIL.value,
             "criticality": "advisory"}]
    decision, blocking = release_decision(rows)
    assert decision == HOLD
    assert blocking == ["a"]


def test_the_blocking_list_names_every_field_that_holds_it():
    contract = new_contract([
        _spec(name="dose", criticality=CRITICAL),
        _spec(name="route", authority=TABLE, source="formulary"),
    ])
    report = check_answer({"dose": _claim(source="nowhere"),
                           "route": {"value": "oral", "source": "formulary"}},
                          contract, {"protocol": lambda _a: 500.0,
                                     "formulary": lambda _a: "intravenous"})
    assert report["release"] == HOLD
    assert sorted(report["blocking"]) == ["dose", "route"]


def test_an_unknown_criticality_is_refused_at_contract_time():
    with pytest.raises(ContractError):
        new_contract([_spec(criticality="quite-important")])
