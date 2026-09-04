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

The reason codes here are the contract's own. `UnverifiableReason` describes
why an oracle could not run, and three of these describe the answer instead.
"""
from __future__ import annotations

from numbers import Real

from .verdict import Verdict

SCHEMA = "flywheel.output-contract-report/v1"

# What kind of thing decides a field. TABLE and RECOMPUTE both yield a value to
# compare against. CITED only requires that the answer name where it looked.
TABLE = "TABLE"
RECOMPUTE = "RECOMPUTE"
CITED = "CITED"
AUTHORITIES = (TABLE, RECOMPUTE, CITED)

AGREES = "AGREES"
DISAGREES = "DISAGREES"
UNCITED = "UNCITED"
FIELD_ABSENT = "FIELD_ABSENT"
OUT_OF_RANGE = "OUT_OF_RANGE"
AUTHORITY_UNAVAILABLE = "AUTHORITY_UNAVAILABLE"

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
        if spec["name"] in seen:
            raise ContractError(f"duplicate field {spec['name']!r}")
        seen.add(spec["name"])
        fields.append({
            "name": spec["name"],
            "authority": spec["authority"],
            "source": spec["source"],
            "tolerance": float(spec.get("tolerance", 0.0)),
            "describes": spec.get("describes", ""),
        })
    return fields


def _agrees(claimed, authoritative, tolerance: float) -> bool:
    """`bool` is checked first because it is an `int` in Python, and True would
    otherwise agree with a tax of one dollar."""
    if isinstance(claimed, bool) or isinstance(authoritative, bool):
        return claimed is authoritative
    if isinstance(claimed, Real) and isinstance(authoritative, Real):
        return abs(float(claimed) - float(authoritative)) <= tolerance
    return claimed == authoritative


def _row(field: dict, verdict: Verdict, code: str, reason: str, cited: bool) -> dict:
    return {"field": field["name"], "authority": field["authority"],
            "source": field["source"], "verdict": verdict.value,
            "code": code, "reason": reason, "cited": cited}


def check_field(field: dict, answer: dict, authorities: dict) -> dict:
    """One field against the authority that decides it.

    No row carries the authoritative value. The report is what feeds the next
    attempt, and an attempt that copies a number the checker handed it has
    consulted nothing. An auditor re-runs the authority instead, which is the
    reason an authority is a function and not a transcription.
    """
    claim = (answer or {}).get(field["name"])
    source = field["source"]
    if not isinstance(claim, dict):
        return _row(field, Verdict.UNVERIFIABLE, FIELD_ABSENT,
                    "the answer states no value for this field", False)
    cited = claim.get("source") == source
    resolve = (authorities or {}).get(source)
    if resolve is None:
        return _row(field, Verdict.UNVERIFIABLE, AUTHORITY_UNAVAILABLE,
                    f"no authority was supplied for {source}", cited)
    if field["authority"] == CITED:
        if cited:
            return _row(field, Verdict.PASS, AGREES,
                        f"the answer cites {source}", True)
        return _row(field, Verdict.UNVERIFIABLE, UNCITED,
                    f"the answer does not cite {source}", False)
    try:
        authoritative = resolve(answer)
    except LookupError as exc:
        return _row(field, Verdict.UNVERIFIABLE, OUT_OF_RANGE,
                    f"{source} does not cover this input: {exc}", cited)
    except Exception as exc:  # noqa: BLE001 - see below
        # An authority that breaks must not take the other fields down with it,
        # and it must not read as a check that passed. The error text rides
        # along in the reason so the break stays visible rather than becoming a
        # quiet unverified.
        return _row(field, Verdict.UNVERIFIABLE, AUTHORITY_UNAVAILABLE,
                    f"{source} could not decide: {type(exc).__name__}: {exc}",
                    cited)
    if not _agrees(claim.get("value"), authoritative, field["tolerance"]):
        return _row(field, Verdict.FAIL, DISAGREES,
                    f"the value disagrees with {source}", cited)
    if not cited:
        return _row(field, Verdict.UNVERIFIABLE, UNCITED,
                    f"the value agrees with {source}, and the answer does not "
                    f"say it came from there", False)
    return _row(field, Verdict.PASS, AGREES, f"the value agrees with {source}", True)


def check_answer(answer: dict, contract: list[dict], authorities: dict) -> dict:
    """Every field, then the worst verdict among them.

    Worst rather than most common. A run where nine fields agree and one
    disagrees with the law is a failing run, and an average would publish it as
    a good one.
    """
    rows = [check_field(field, answer, authorities) for field in contract]
    verdicts = [row["verdict"] for row in rows]
    if Verdict.FAIL.value in verdicts:
        overall = Verdict.FAIL
    elif Verdict.UNVERIFIABLE.value in verdicts:
        overall = Verdict.UNVERIFIABLE
    else:
        overall = Verdict.PASS
    return {
        "schema": SCHEMA,
        "verdict": overall.value,
        "checked": len(rows),
        "passed": verdicts.count(Verdict.PASS.value),
        "unresolved": [row["field"] for row in rows
                       if row["verdict"] != Verdict.PASS.value],
        "fields": rows,
    }


# What the next attempt is told to do about each way a field can fail. Each
# instruction points at the authority. None of them supplies a value, so a
# passing retry is one that went and looked.
_INSTRUCTION = {
    DISAGREES: "consult {source} and take the value it gives, rather than "
               "deriving one that should match it",
    UNCITED: "name the source the value came from; {source} is what decides it",
    FIELD_ABSENT: "state a value for this field, from {source}",
    OUT_OF_RANGE: "{source} does not cover this input, so say so rather than "
                  "deriving a value it cannot confirm",
    AUTHORITY_UNAVAILABLE: "{source} was not available to the checker, so this "
                           "field is unchecked rather than wrong",
}


def feedback(report: dict) -> dict:
    """The unresolved fields, shaped for the next attempt to act on.

    Structured rather than prose because the next attempt has to act on it, and
    a paragraph of criticism is something a model can agree with and then
    ignore. Passing fields are dropped: re-litigating them invites a rewrite
    that breaks one.
    """
    fields = []
    for row in report["fields"]:
        if row["verdict"] == Verdict.PASS.value:
            continue
        fields.append({
            "field": row["field"],
            "verdict": row["verdict"],
            "code": row["code"],
            "source": row["source"],
            "reason": row["reason"],
            "do": _INSTRUCTION[row["code"]].format(source=row["source"]),
        })
    return {"verdict": report["verdict"], "fields": fields}
