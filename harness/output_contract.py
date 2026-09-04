"""output_contract.py -- what an answer must satisfy before anyone reads it.

A model that checks its own arithmetic re-derives the same wrong number. The
tax case is the clean example: on taxable income of $36,700 the rate schedule
gives $4,165.50 and the tax table gives $4,169, and the table is the one the
form requires. Both figures survive any amount of recomputation, because the
method chose the wrong authority and the arithmetic was never the problem.

So a contract binds each claimed field to the authority that decides it, and
the check runs against that authority rather than against the reasoning that
produced the value. Three outcomes, and the third is the one usually rounded
away:

    the value disagrees with the authority         FAIL
    the value agrees and the answer says why       PASS
    the value agrees and nothing binds it there    UNVERIFIABLE

The last is not pedantry. A right answer nobody can trace is right this once.

Five authorities, because a regulated answer fails in five ways and a value
comparison catches one of them. TABLE and RECOMPUTE produce a value. CITED
requires the answer to name where it looked. UNIT decides what the number is
measured in, which is how a milligram becomes a microgram. BOUND decides
whether a value is permitted at all, which is how a correctly computed dose
exceeds a ceiling.

Above all of them sits the method mandate. A field may declare the method its
domain requires, and an answer that reached the right number by the wrong
method still fails. That is the 1040 case stated in general terms, and it
repeats wherever the law names a procedure: Cockcroft-Gault against CKD-EPI,
30/360 against actual/365, calendar days against court days.

The vocabulary lives in `contract_terms`, the per-field decisions in
`contract_checks`, and the next attempt's instructions in `contract_feedback`.
This module holds what a contract is and what a report says.
"""
from __future__ import annotations

from .contract_checks import (agrees as _agrees, ask, bound_row, method_row,
                              row, unit_row, value_row)
from .contract_terms import (ADVISORY, AGREES, AUTHORITIES,
                             AUTHORITY_UNAVAILABLE, BOUND, CITED, CRITICAL,
                             CRITICALITIES, DISAGREES, FIELD_ABSENT, HOLD,
                             METHOD_MISMATCH, METHOD_UNSTATED, OUT_OF_BOUND,
                             OUT_OF_RANGE, RECOMPUTE, RELEASE,
                             RELEASE_WITH_CAVEAT, SCHEMA, STANDARD, TABLE,
                             UNCITED, UNIT, UNIT_MISMATCH, UNIT_UNSTATED)
from .verdict import Verdict

_REQUIRED = ("name", "authority", "source")


class ContractError(ValueError):
    """Raised on a contract no answer could meaningfully be checked against."""


def new_contract(specs: list[dict]) -> list[dict]:
    """Freeze a list of field specs into a contract.

    Refuses an empty contract for the same reason `new_criteria` does: a
    contract that requires nothing accepts everything, which is the state the
    caller was already in.
    """
    if not specs:
        raise ContractError("a contract that requires nothing accepts everything")
    seen: set[str] = set()
    fields: list[dict] = []
    for spec in specs:
        missing = [key for key in _REQUIRED if not spec.get(key)]
        if missing:
            raise ContractError(f"field spec missing {', '.join(missing)}")
        if spec["authority"] not in AUTHORITIES:
            raise ContractError(f"unknown authority {spec['authority']!r}")
        criticality = spec.get("criticality", STANDARD)
        if criticality not in CRITICALITIES:
            raise ContractError(f"unknown criticality {criticality!r}")
        if spec["name"] in seen:
            raise ContractError(f"duplicate field {spec['name']!r}")
        seen.add(spec["name"])
        fields.append({
            "name": spec["name"],
            "authority": spec["authority"],
            "source": spec["source"],
            "tolerance": float(spec.get("tolerance", 0.0)),
            "criticality": criticality,
            "method": spec.get("method", ""),
            "describes": spec.get("describes", ""),
        })
    return fields


def check_field(field: dict, answer: dict, authorities: dict) -> dict:
    """One field against the authority that decides it.

    The method mandate runs before the value, because a number reached the
    wrong way is wrong even on the runs where it matches.
    """
    claim = (answer or {}).get(field["name"])
    source = field["source"]
    if not isinstance(claim, dict):
        return row(field, Verdict.UNVERIFIABLE, FIELD_ABSENT,
                   "the answer states no value for this field", False)
    cited = claim.get("source") == source
    resolve = (authorities or {}).get(source)
    if resolve is None:
        return row(field, Verdict.UNVERIFIABLE, AUTHORITY_UNAVAILABLE,
                   f"no authority was supplied for {source}", cited)
    wrong_method = method_row(field, claim, cited)
    if wrong_method is not None:
        return wrong_method
    if field["authority"] == CITED:
        if cited:
            return row(field, Verdict.PASS, AGREES,
                       f"the answer cites {source}", True)
        return row(field, Verdict.UNVERIFIABLE, UNCITED,
                   f"the answer does not cite {source}", False)
    decided, failed = ask(field, answer, resolve, cited)
    if failed is not None:
        return failed
    if field["authority"] == BOUND:
        return bound_row(field, decided, cited)
    if field["authority"] == UNIT:
        return unit_row(field, claim, decided, cited)
    return value_row(field, claim, decided, cited)


def release_decision(rows: list[dict]) -> tuple[str, list[str]]:
    """Whether this answer may leave the building, and what stops it.

    Separate from the verdict and strictly narrower. A FAIL always holds. A
    critical field that reached anything other than PASS also holds, which is
    the whole reason criticality exists. Nothing here can turn a FAIL into a
    release, so a contract author can only make the outcome stricter.
    """
    blocking = [r["field"] for r in rows
                if r["verdict"] == Verdict.FAIL.value
                or (r.get("criticality") == CRITICAL
                    and r["verdict"] != Verdict.PASS.value)]
    if blocking:
        return HOLD, blocking
    if any(r["verdict"] != Verdict.PASS.value for r in rows):
        return RELEASE_WITH_CAVEAT, []
    return RELEASE, []


def check_answer(answer: dict, contract: list[dict], authorities: dict) -> dict:
    """Every field, then the worst verdict among them.

    Worst rather than most common. A run where nine fields agree and one
    disagrees with the law is a failing run, and an average would publish it as
    a good one.
    """
    rows = [check_field(field, answer, authorities) for field in contract]
    verdicts = [r["verdict"] for r in rows]
    if Verdict.FAIL.value in verdicts:
        overall = Verdict.FAIL
    elif Verdict.UNVERIFIABLE.value in verdicts:
        overall = Verdict.UNVERIFIABLE
    else:
        overall = Verdict.PASS
    release, blocking = release_decision(rows)
    return {
        "schema": SCHEMA,
        "verdict": overall.value,
        "release": release,
        "blocking": blocking,
        "checked": len(rows),
        "passed": verdicts.count(Verdict.PASS.value),
        "unresolved": [r["field"] for r in rows
                       if r["verdict"] != Verdict.PASS.value],
        "fields": rows,
    }
