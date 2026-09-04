"""contract_checks.py -- how one claimed field is decided.

Split out of `output_contract` so the contract module holds what a contract is
and what a report says, and this one holds the five ways a field can be wrong.
Nothing here reads a whole contract, and nothing here decides a release.

Every function returns a row. No row carries the authoritative value, which is
the most load-bearing property in the feature: rows feed the next attempt, and
an attempt that copies a number out of its own failure report has consulted
nothing and learned the opposite lesson.
"""
from __future__ import annotations

from numbers import Real

from .contract_terms import (AGREES, AUTHORITY_UNAVAILABLE, DISAGREES,
                             METHOD_MISMATCH, METHOD_UNSTATED, OUT_OF_BOUND,
                             OUT_OF_RANGE, STANDARD, UNCITED, UNIT_MISMATCH,
                             UNIT_UNSTATED)
from .verdict import Verdict


def agrees(claimed, authoritative, tolerance: float) -> bool:
    """`bool` is checked first because it is an `int` in Python, and True would
    otherwise agree with a tax of one dollar."""
    if isinstance(claimed, bool) or isinstance(authoritative, bool):
        return claimed is authoritative
    if isinstance(claimed, Real) and isinstance(authoritative, Real):
        return abs(float(claimed) - float(authoritative)) <= tolerance
    return claimed == authoritative


def row(field: dict, verdict: Verdict, code: str, reason: str, cited: bool) -> dict:
    return {"field": field["name"], "authority": field["authority"],
            "source": field["source"], "verdict": verdict.value,
            "code": code, "reason": reason, "cited": cited,
            "criticality": field.get("criticality", STANDARD),
            "method": field.get("method", "")}


def method_row(field: dict, claim: dict, cited: bool) -> dict | None:
    """The method mandate, checked before the value.

    A field that names no method skips this. Where the domain does name one, an
    answer that reached the number some other way is wrong about the thing that
    matters, and it stays wrong on the occasions when the two methods happen to
    agree. Those occasions are exactly what must not be allowed to pass.
    """
    required = field.get("method", "")
    if not required:
        return None
    stated = claim.get("method", "")
    if not stated:
        return row(field, Verdict.UNVERIFIABLE, METHOD_UNSTATED,
                   f"the answer does not say which method produced this, and "
                   f"{field['source']} requires {required}", cited)
    if stated != required:
        return row(field, Verdict.FAIL, METHOD_MISMATCH,
                   f"the answer used {stated} where {field['source']} "
                   f"requires {required}", cited)
    return None


def ask(field: dict, answer: dict, resolve, cited: bool):
    """Ask the authority. Returns `(value, None)` or `(None, row)`."""
    try:
        return resolve(answer), None
    except LookupError as exc:
        return None, row(field, Verdict.UNVERIFIABLE, OUT_OF_RANGE,
                         f"{field['source']} does not cover this input: {exc}",
                         cited)
    except Exception as exc:  # noqa: BLE001 - see below
        # An authority that breaks must not take the other fields down with it,
        # and it must not read as a check that passed. The error text rides
        # along in the reason so the break stays visible rather than becoming a
        # quiet unverified.
        return None, row(field, Verdict.UNVERIFIABLE, AUTHORITY_UNAVAILABLE,
                         f"{field['source']} could not decide: "
                         f"{type(exc).__name__}: {exc}", cited)


def bound_row(field: dict, decision, cited: bool) -> dict:
    """A permission decision. `True`, `False`, or `(ok, reason)`.

    A dose can be arithmetically perfect and still sit above the ceiling the
    formulary sets, and a filing can be correctly dated and still fall past the
    deadline. Neither is a value disagreement, so both get their own code.
    """
    reason = ""
    if isinstance(decision, tuple):
        decision, reason = decision[0], str(decision[1])
    if decision:
        return row(field, Verdict.PASS, AGREES,
                   reason or f"{field['source']} permits this value", cited)
    return row(field, Verdict.FAIL, OUT_OF_BOUND,
               reason or f"{field['source']} does not permit this value", cited)


def unit_row(field: dict, claim: dict, required, cited: bool) -> dict:
    """The unit the value is measured in, which the value alone never states.

    A thousandfold error reads as a plausible number, so an absent unit is
    UNVERIFIABLE rather than wrong. Criticality turns that into a hold.
    """
    stated = claim.get("unit", "")
    if not stated:
        return row(field, Verdict.UNVERIFIABLE, UNIT_UNSTATED,
                   f"the answer states no unit, and {field['source']} "
                   f"requires {required}", cited)
    if stated != required:
        return row(field, Verdict.FAIL, UNIT_MISMATCH,
                   f"the answer states {stated} where {field['source']} "
                   f"requires {required}", cited)
    return row(field, Verdict.PASS, AGREES,
               f"the unit agrees with {field['source']}", cited)


def value_row(field: dict, claim: dict, authoritative, cited: bool) -> dict:
    if not agrees(claim.get("value"), authoritative, field["tolerance"]):
        return row(field, Verdict.FAIL, DISAGREES,
                   f"the value disagrees with {field['source']}", cited)
    if not cited:
        return row(field, Verdict.UNVERIFIABLE, UNCITED,
                   f"the value agrees with {field['source']}, and the answer "
                   f"does not say it came from there", False)
    return row(field, Verdict.PASS, AGREES,
               f"the value agrees with {field['source']}", True)
