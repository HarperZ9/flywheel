"""finance.py -- the financial pack.

Ships no rate table and no tax table. It ships the mandates that make using the
wrong one visible, and the day-count and rounding arithmetic that a contract
needs in order to have an opinion at all.

The failures it is built around:

    the rate schedule was used where the tax table governs
    30/360 was used where the note says actual/365
    half-even rounding was used where the rule says half-up
    a yen amount was carried to two decimals
"""
from __future__ import annotations

from datetime import date

from ..contract_terms import BOUND, CITED, RECOMPUTE, STANDARD, TABLE, UNIT
from .pack import Pack, Template
from .units import HALF_UP, minor_units, round_to

# The conventions a field may mandate. Names, so a contract can say which one
# governs and a mismatch is a FAIL rather than a rounding difference.
THIRTY_360 = "30/360"
ACTUAL_360 = "actual/360"
ACTUAL_365 = "actual/365"
ACTUAL_ACTUAL = "actual/actual"
DAY_COUNTS = (THIRTY_360, ACTUAL_360, ACTUAL_365, ACTUAL_ACTUAL)


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def year_fraction(convention: str, start, end) -> float:
    """The fraction of a year between two dates, by the named convention.

    Two notes on the same principal and rate accrue different interest under
    different conventions, and the difference is real money over a long term.
    Which one governs is in the instrument, never in the arithmetic.
    """
    start, end = _as_date(start), _as_date(end)
    if convention == THIRTY_360:
        d1 = min(start.day, 30)
        d2 = min(end.day, 30) if d1 == 30 else end.day
        return (360 * (end.year - start.year) + 30 * (end.month - start.month)
                + (d2 - d1)) / 360.0
    days = (end - start).days
    if convention == ACTUAL_360:
        return days / 360.0
    if convention == ACTUAL_365:
        return days / 365.0
    if convention == ACTUAL_ACTUAL:
        total = 0.0
        cursor = start
        while cursor < end:
            boundary = min(date(cursor.year + 1, 1, 1), end)
            length = (date(cursor.year + 1, 1, 1) - date(cursor.year, 1, 1)).days
            total += (boundary - cursor).days / length
            cursor = boundary
        return total
    raise LookupError(f"unknown day-count convention {convention!r}; "
                      f"known: {list(DAY_COUNTS)}")


def accrual_authority(convention: str, *, reads: str = "terms",
                      places: int = 2, mode: str = HALF_UP):
    """A RECOMPUTE authority for simple interest under a named convention.

    Reads principal, rate, start and end from the answer's own terms block, so
    the authority recomputes from the same inputs and can only disagree about
    the method and the arithmetic.
    """
    def resolve(answer: dict):
        terms = (answer or {}).get(reads)
        if not isinstance(terms, dict):
            raise LookupError(f"the answer carries no {reads!r} block")
        try:
            principal = float(terms["principal"])
            rate = float(terms["rate"])
            start, end = terms["start"], terms["end"]
        except (KeyError, TypeError, ValueError) as exc:
            raise LookupError(f"{reads} is missing principal, rate, start or "
                              f"end: {exc}") from None
        return round_to(principal * rate * year_fraction(convention, start, end),
                        places, mode)
    return resolve


def currency_rounding_authority(reads: str, *, currency_key: str = "currency",
                                mode: str = HALF_UP):
    """A RECOMPUTE authority that rounds a claimed amount to its own currency.

    Catches the amount carried to more places than the currency has. A yen
    figure with a decimal point is not a small presentation problem, it is a
    number that cannot be paid.
    """
    def resolve(answer: dict):
        claim = (answer or {}).get(reads)
        if not isinstance(claim, dict) or claim.get("value") is None:
            raise LookupError(f"the answer states no value for {reads!r}")
        code = (answer or {}).get(currency_key)
        if not code:
            raise LookupError(f"the answer states no {currency_key!r}, so the "
                              f"number of decimal places is undecided")
        return round_to(claim["value"], minor_units(str(code)), mode)
    return resolve


CAUTION = (
    "This pack decides nothing about what the law charges. It holds no rate "
    "schedule, no tax table, no filing threshold and no jurisdiction rule. "
    "Supply those as authorities. What the pack contributes is the mandate "
    "that names which one governs, and the arithmetic underneath it."
)

PACK = Pack(
    name="finance",
    describes="regulated financial answers: tax, interest, payroll, currency",
    caution=CAUTION,
    templates={
        "statutory_amount": Template(
            "statutory_amount", TABLE, method="table-lookup",
            describes="an amount a published table decides, not a formula",
            catches="the rate schedule used where the tax table governs"),
        "accrued_interest": Template(
            "accrued_interest", RECOMPUTE, method=ACTUAL_365,
            describes="interest over a period under a named day count",
            catches="30/360 used where the instrument says actual/365"),
        "currency": Template(
            "currency", UNIT,
            describes="the currency an amount is denominated in",
            catches="a figure reported without saying which currency"),
        "minor_units": Template(
            "minor_units", RECOMPUTE, criticality=STANDARD,
            method="iso-4217-minor-units",
            describes="an amount rounded to its currency's decimal places",
            catches="a yen amount carried to two decimals"),
        "threshold": Template(
            "threshold", BOUND,
            describes="whether an amount is inside a statutory limit",
            catches="a correctly computed figure that exceeds a cap"),
        "authority_cited": Template(
            "authority_cited", CITED,
            describes="the published source the figure came from",
            catches="a right number nobody can trace"),
    },
)
