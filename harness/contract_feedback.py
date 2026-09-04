"""contract_feedback.py -- what the next attempt is told to do.

Structured rather than prose, because the next attempt has to act on it and a
paragraph of criticism is something a model can agree with and then ignore.

Not one instruction supplies a value. A retry that copied the number out of its
own failure report would pass the check while learning the opposite lesson, so
every instruction points at the authority and stops there.
"""
from __future__ import annotations

from .contract_terms import (AUTHORITY_UNAVAILABLE, DISAGREES, FIELD_ABSENT,
                             METHOD_MISMATCH, METHOD_UNSTATED, OUT_OF_BOUND,
                             OUT_OF_RANGE, UNCITED, UNIT_MISMATCH,
                             UNIT_UNSTATED)
from .verdict import Verdict

_INSTRUCTION = {
    DISAGREES: "consult {source} and take the value it gives, rather than "
               "deriving one that should match it",
    UNCITED: "name the source the value came from; {source} is what decides it",
    FIELD_ABSENT: "state a value for this field, from {source}",
    OUT_OF_RANGE: "{source} does not cover this input, so say so rather than "
                  "deriving a value it cannot confirm",
    AUTHORITY_UNAVAILABLE: "{source} was not available to the checker, so this "
                           "field is unchecked rather than wrong",
    METHOD_MISMATCH: "redo this by the method {source} requires; a number "
                     "reached another way is wrong even where it matches",
    METHOD_UNSTATED: "state which method produced this value, and use the one "
                     "{source} requires",
    UNIT_MISMATCH: "restate this in the unit {source} requires, and convert "
                   "the value rather than relabelling it",
    UNIT_UNSTATED: "state the unit this value is in; {source} decides which "
                   "one it has to be",
    OUT_OF_BOUND: "{source} does not permit this value, so the answer needs a "
                  "different one rather than a better derivation of this one",
}


def feedback(report: dict) -> dict:
    """The unresolved fields, shaped for the next attempt to act on.

    Passing fields are dropped. Re-litigating them invites a rewrite that
    breaks one.
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
            "criticality": row.get("criticality", ""),
            "reason": row["reason"],
            "do": _INSTRUCTION[row["code"]].format(source=row["source"]),
        })
    return {"verdict": report["verdict"],
            "release": report.get("release", ""),
            "blocking": report.get("blocking", []),
            "fields": fields}
