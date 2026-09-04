"""law.py -- the legal pack.

Ships no case law, no statute text, no citation list and no court calendar. A
fabricated citation is the best-documented failure mode of a language model in
this domain, and a library that carried its own citation list would be handing
one back with a straight face.

What it ships is deadline arithmetic against a calendar the caller supplies,
and the mandates that make the calendar question unavoidable. A deadline
computed in calendar days where the rule counts court days is wrong by the
number of weekends and holidays in between, and it is wrong in the direction
that misses the filing.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..contract_terms import BOUND, CITED, RECOMPUTE, STANDARD
from .pack import Pack, Template

CALENDAR_DAYS = "calendar-days"
COURT_DAYS = "court-days"
BUSINESS_DAYS = "business-days"
COUNTING_RULES = (CALENDAR_DAYS, COURT_DAYS, BUSINESS_DAYS)

# Saturday and Sunday, as `date.weekday()` numbers them. A jurisdiction whose
# weekend falls elsewhere passes its own.
DEFAULT_WEEKEND = (5, 6)


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def add_days(start, count: int, *, rule: str = CALENDAR_DAYS,
             holidays=(), weekend=DEFAULT_WEEKEND) -> date:
    """Advance a date by a count under a named counting rule.

    Holidays are the caller's list. An empty list is not a claim that there are
    no holidays, it is a claim that the caller supplied none, which is why a
    deadline field is critical and an unsupplied calendar holds the answer.
    """
    if rule not in COUNTING_RULES:
        raise LookupError(f"unknown counting rule {rule!r}; "
                          f"known: {list(COUNTING_RULES)}")
    cursor = _as_date(start)
    if rule == CALENDAR_DAYS:
        return cursor + timedelta(days=count)
    closed = {_as_date(h) for h in holidays}
    step = 1 if count >= 0 else -1
    remaining = abs(count)
    while remaining:
        cursor += timedelta(days=step)
        if cursor.weekday() in weekend or cursor in closed:
            continue
        remaining -= 1
    return cursor


def deadline_authority(count: int, *, rule: str = CALENDAR_DAYS,
                       reads: str = "trigger", holidays=(),
                       weekend=DEFAULT_WEEKEND):
    """A RECOMPUTE authority for a deadline, returned as an ISO date string.

    Reads the triggering date from the answer, so the authority and the answer
    start from the same fact and can only disagree about the counting.
    """
    def resolve(answer: dict):
        claim = (answer or {}).get(reads)
        raw = claim.get("value") if isinstance(claim, dict) else claim
        if not raw:
            raise LookupError(f"the answer states no {reads!r} date to count from")
        return add_days(raw, count, rule=rule, holidays=holidays,
                        weekend=weekend).isoformat()
    return resolve


def within_period_authority(count: int, *, rule: str = CALENDAR_DAYS,
                            reads_start: str = "accrual",
                            reads_filed: str = "filed", holidays=(),
                            weekend=DEFAULT_WEEKEND):
    """A BOUND authority for whether a filing date is still inside a period."""
    def resolve(answer: dict):
        def read(key):
            claim = (answer or {}).get(key)
            raw = claim.get("value") if isinstance(claim, dict) else claim
            if not raw:
                raise LookupError(f"the answer states no {key!r} date")
            return _as_date(raw)
        last = add_days(read(reads_start), count, rule=rule, holidays=holidays,
                        weekend=weekend)
        filed = read(reads_filed)
        if filed <= last:
            return True, f"filed on or before {last.isoformat()}"
        return False, f"the period closed on {last.isoformat()}"
    return resolve


CAUTION = (
    "This pack is not a legal authority. It carries no statutes, no case law, "
    "no citations and no court calendar. Citations must resolve against a "
    "registry the caller supplies, and holidays must be passed in. What the "
    "pack contributes is the counting, and the mandate that says which count "
    "governs."
)

PACK = Pack(
    name="law",
    describes="legal answers: deadlines, limitations periods, citations",
    caution=CAUTION,
    templates={
        "deadline": Template(
            "deadline", RECOMPUTE, method=COURT_DAYS,
            describes="a filing deadline under the mandated counting rule",
            catches="calendar days counted where the rule counts court days"),
        "within_period": Template(
            "within_period", BOUND,
            describes="whether a filing falls inside the limitations period",
            catches="a correctly formatted filing made after the period closed"),
        "citation": Template(
            "citation", CITED,
            describes="an authority that must resolve in a real registry",
            catches="a citation that reads correctly and does not exist"),
        "jurisdiction": Template(
            "jurisdiction", CITED,
            describes="the jurisdiction whose rule was applied",
            catches="one state's rule applied to another state's filing"),
        "service_date": Template(
            "service_date", RECOMPUTE, criticality=STANDARD,
            method=CALENDAR_DAYS,
            describes="a service or notice date derived from a trigger",
            catches="a notice period counted from the wrong trigger"),
    },
)
