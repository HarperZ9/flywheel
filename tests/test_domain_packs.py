"""Falsifiers for the domain packs.

Two things are under test. The arithmetic, which has to be right because a
deadline off by a weekend misses a filing. And the standing rule that a pack
ships no domain data, which is the property that keeps the packs honest: a
library that carried its own dose ceiling would be asking a reader to trust a
number whose provenance is a commit message.
"""
import pytest

from harness.contract_terms import CRITICAL
from harness.domain_packs import (contract_from, load_pack, pack_names,
                                  pack_report, unsupplied)
from harness.domain_packs import finance, law, medicine, units
from harness.output_contract import check_answer
from harness.verdict import Verdict


# --- the registry ----------------------------------------------------------

def test_the_three_critical_domains_are_present():
    assert pack_names() == ["finance", "law", "medicine"]


def test_an_unknown_pack_raises_rather_than_returning_an_empty_one():
    with pytest.raises(LookupError):
        load_pack("aviation")


def test_every_template_says_what_it_catches():
    """A template with no named failure is a shape nobody chose on purpose."""
    for name in pack_names():
        pack = load_pack(name)
        for key, tpl in pack.templates.items():
            assert tpl.catches, f"{name}:{key} names no failure"


def test_a_pack_report_leads_with_the_caution():
    text = pack_report(load_pack("medicine"))
    assert text.index("not a clinical authority") < text.index("dose")


def test_no_pack_ships_domain_data():
    """The load-bearing rule, checked rather than asserted in a docstring.

    A pack may hold method names, unit factors and rounding modes. It may not
    hold a dose, a rate, a ceiling or a citation. Numbers that appear in these
    modules belong to arithmetic conventions, so the check is that no pack
    exposes a mapping of domain terms to authoritative values.
    """
    for module in (medicine, law):
        numeric = {k: v for k, v in vars(module).items()
                   if not k.startswith("_") and isinstance(v, (int, float))
                   and not isinstance(v, bool)}
        assert not numeric, f"{module.__name__} exposes numbers: {sorted(numeric)}"


# --- units -----------------------------------------------------------------

def test_pounds_convert_to_kilograms():
    assert round(units.convert(154.0, "lb", "kg"), 3) == 69.853


def test_milligrams_to_micrograms_is_a_thousandfold():
    assert units.convert(1.0, "mg", "mcg") == pytest.approx(1000.0)


def test_a_conversion_that_needs_a_molar_mass_is_refused():
    with pytest.raises(LookupError) as exc:
        units.convert(1.0, "mmol", "mg")
    assert "substance-specific constant" in str(exc.value)


def test_an_unknown_unit_raises_rather_than_passing_through():
    with pytest.raises(LookupError):
        units.convert(1.0, "smidgen", "mg")


def test_half_up_and_half_even_disagree_on_the_midpoint():
    assert units.round_to(2.5, 0, units.HALF_UP) == 3.0
    assert units.round_to(2.5, 0, units.HALF_EVEN) == 2.0
    assert units.round_to(2.5, 0, units.TRUNCATE) == 2.0


def test_yen_has_no_minor_units_and_dinars_have_three():
    assert units.minor_units("JPY") == 0
    assert units.minor_units("KWD") == 3
    assert units.minor_units("usd") == 2


def test_an_unlisted_currency_raises_rather_than_defaulting_to_two():
    with pytest.raises(LookupError) as exc:
        units.minor_units("XTS")
    assert "rather than assuming two" in str(exc.value)


def test_a_ceiling_converts_the_stated_unit_before_comparing():
    ceiling = units.ceiling_authority("dose", 3000.0, "mg")
    ok, _ = ceiling({"dose": {"value": 4.0, "unit": "g"}})
    assert ok is False
    ok, _ = ceiling({"dose": {"value": 2.0, "unit": "g"}})
    assert ok is True


def test_a_ceiling_over_a_field_the_answer_omits_raises():
    ceiling = units.ceiling_authority("dose", 3000.0, "mg")
    with pytest.raises(LookupError):
        ceiling({"weight": {"value": 70.0}})


# --- finance ---------------------------------------------------------------

def test_the_day_counts_disagree_over_the_same_period():
    start, end = "2026-01-01", "2026-07-01"
    thirty = finance.year_fraction(finance.THIRTY_360, start, end)
    a365 = finance.year_fraction(finance.ACTUAL_365, start, end)
    assert thirty == pytest.approx(0.5)
    assert a365 == pytest.approx(181 / 365)
    assert thirty != a365


def test_actual_360_pays_more_than_actual_365_over_the_same_days():
    start, end = "2026-01-01", "2026-12-31"
    assert (finance.year_fraction(finance.ACTUAL_360, start, end)
            > finance.year_fraction(finance.ACTUAL_365, start, end))


def test_actual_actual_splits_at_the_year_boundary():
    frac = finance.year_fraction(finance.ACTUAL_ACTUAL, "2027-12-01",
                                 "2028-02-01")
    assert frac == pytest.approx(31 / 365 + 31 / 366, abs=1e-9)


def test_an_unknown_convention_raises():
    with pytest.raises(LookupError):
        finance.year_fraction("30/365-ish", "2026-01-01", "2026-02-01")


def test_the_wrong_day_count_is_a_failing_answer_not_a_rounding_difference():
    contract = contract_from(load_pack("finance"), [
        {"use": "accrued_interest", "name": "interest", "source": "note"}])
    answer = {"terms": {"principal": 100000.0, "rate": 0.05,
                        "start": "2026-01-01", "end": "2026-07-01"},
              "interest": {"value": 2500.0, "source": "note",
                           "method": finance.THIRTY_360}}
    report = check_answer(answer, contract,
                          {"note": finance.accrual_authority(finance.ACTUAL_365)})
    assert report["verdict"] == Verdict.FAIL.value
    assert report["release"] == "HOLD"


def test_a_yen_amount_carried_to_two_decimals_disagrees():
    rounder = finance.currency_rounding_authority("total")
    answer = {"currency": "JPY", "total": {"value": 1250.55}}
    assert rounder(answer) == 1251.0


def test_an_amount_with_no_stated_currency_cannot_be_rounded():
    rounder = finance.currency_rounding_authority("total")
    with pytest.raises(LookupError):
        rounder({"total": {"value": 1250.55}})


# --- law -------------------------------------------------------------------

def test_calendar_days_and_court_days_land_on_different_dates():
    start = "2026-09-04"          # a Friday
    calendar = law.add_days(start, 5, rule=law.CALENDAR_DAYS)
    court = law.add_days(start, 5, rule=law.COURT_DAYS)
    assert calendar.isoformat() == "2026-09-09"
    assert court.isoformat() == "2026-09-11"


def test_a_supplied_holiday_pushes_a_court_deadline_out():
    start = "2026-09-04"
    without = law.add_days(start, 5, rule=law.COURT_DAYS)
    with_holiday = law.add_days(start, 5, rule=law.COURT_DAYS,
                                holidays=["2026-09-07"])
    assert with_holiday > without


def test_counting_backwards_skips_weekends_too():
    back = law.add_days("2026-09-07", -1, rule=law.BUSINESS_DAYS)
    assert back.isoformat() == "2026-09-04"


def test_an_unknown_counting_rule_raises():
    with pytest.raises(LookupError):
        law.add_days("2026-09-04", 5, rule="whenever")


def test_a_deadline_counted_in_calendar_days_fails_a_court_day_contract():
    contract = contract_from(load_pack("law"), [
        {"use": "deadline", "name": "due", "source": "rule-6"}])
    answer = {"trigger": {"value": "2026-09-04"},
              "due": {"value": "2026-09-09", "source": "rule-6",
                      "method": law.COURT_DAYS}}
    report = check_answer(answer, contract,
                          {"rule-6": law.deadline_authority(5, rule=law.COURT_DAYS)})
    assert report["verdict"] == Verdict.FAIL.value


def test_a_deadline_with_no_trigger_date_is_unverifiable_not_wrong():
    contract = contract_from(load_pack("law"), [
        {"use": "deadline", "name": "due", "source": "rule-6"}])
    answer = {"due": {"value": "2026-09-11", "source": "rule-6",
                      "method": law.COURT_DAYS}}
    report = check_answer(answer, contract,
                          {"rule-6": law.deadline_authority(5, rule=law.COURT_DAYS)})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value


def test_a_filing_past_the_limitations_period_is_out_of_bound():
    within = law.within_period_authority(365, rule=law.CALENDAR_DAYS)
    ok, reason = within({"accrual": {"value": "2025-01-01"},
                         "filed": {"value": "2026-06-01"}})
    assert ok is False
    assert "2026-01-01" in reason


# --- medicine --------------------------------------------------------------

def test_a_weight_based_dose_converts_a_weight_stated_in_pounds():
    dose = medicine.weight_based_authority(10.0, unit="mg")
    assert dose({"weight": {"value": 154.0, "unit": "lb"}}) == pytest.approx(698.5)


def test_the_cap_applies_after_the_multiply_not_before():
    dose = medicine.weight_based_authority(10.0, cap=600.0)
    assert dose({"weight": {"value": 90.0, "unit": "kg"}}) == 600.0


def test_a_dose_with_no_stated_weight_raises_rather_than_assuming_one():
    dose = medicine.weight_based_authority(10.0)
    with pytest.raises(LookupError):
        dose({})


def test_a_declared_source_with_nothing_behind_it_names_itself():
    absent = medicine.absent_authority("formulary:2026-03")
    with pytest.raises(LookupError) as exc:
        absent({})
    assert "formulary:2026-03" in str(exc.value)


def test_a_critical_field_with_no_authority_holds_the_answer():
    contract = contract_from(load_pack("medicine"), [
        {"use": "dose", "name": "dose", "source": "formulary:2026-03"}])
    answer = {"dose": {"value": 500.0, "source": "formulary:2026-03",
                       "method": medicine.BAND_LOOKUP}}
    report = check_answer(answer, contract, {})
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["release"] == "HOLD"
    assert report["blocking"] == ["dose"]


# --- the pre-flight manifest -----------------------------------------------

def test_unsupplied_names_the_gaps_before_an_attempt_is_made():
    contract = contract_from(load_pack("medicine"), [
        {"use": "dose", "name": "dose", "source": "formulary:2026-03"},
        {"use": "maximum", "name": "dose_max", "source": "formulary:max-daily"},
    ])
    gaps = unsupplied(contract, {"formulary:2026-03": lambda _a: 500.0})
    assert [g["field"] for g in gaps] == ["dose_max"]


def test_unsupplied_puts_the_critical_gaps_first():
    contract = contract_from(load_pack("finance"), [
        {"use": "minor_units", "name": "rounded", "source": "iso"},
        {"use": "statutory_amount", "name": "tax", "source": "table"},
    ])
    gaps = unsupplied(contract, {})
    assert gaps[0]["criticality"] == CRITICAL
    assert gaps[0]["field"] == "tax"


def test_an_empty_authority_map_leaves_every_field_unsupplied():
    contract = contract_from(load_pack("law"), [
        {"use": "citation", "name": "cite", "source": "reporter"}])
    assert len(unsupplied(contract, {})) == 1
