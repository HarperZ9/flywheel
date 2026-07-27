"""acceptance_criteria.py -- criteria that only a NAMED oracle can flip.

An agent loop that grades its own "done" claim can talk itself past a bar it
never cleared. This module is the fix: a criterion starts FAILING, and the
only function that can move it is apply_oracle_result, and only when the
caller's `oracle` string matches the oracle name registered on that criterion
at creation time. A model's prose is never that string; it is a name a human
or a real check (pytest, check_writing.py, ...) supplies. That keeps "the
loop reports done" and "the criterion is PASSING" two separate facts.

Single-mutation-point discipline: there is exactly one place in this file's
source that assigns to a criterion's "status" key -- inside
apply_oracle_result. tests/test_acceptance_criteria.py greps this file and
asserts that count is 1. A second assignment site would be a second place a
criterion could flip, silently reopening the exact hole this module exists
to close, so the count is the enforcement, not a description of intent.
"""
from __future__ import annotations

FAILING = "FAILING"
PASSING = "PASSING"

_REQUIRED_SPEC_FIELDS = ("id", "description", "oracle")


class CriteriaError(ValueError):
    """Raised on a malformed criteria set or an unauthorized flip attempt."""


def new_criteria(specs: list[dict]) -> list[dict]:
    """Build a criteria set from specs, each becoming a Criterion dict.

    Every criterion is created FAILING with no evidence, regardless of
    what the spec says -- a spec's own "status" key (if present) is ignored,
    so a caller cannot hand a criterion in already PASSING. Raises
    CriteriaError on an empty list, a spec missing a required field, or a
    duplicate id.
    """
    if not specs:
        raise CriteriaError("a criteria set that requires nothing accepts everything")

    seen_ids: set[str] = set()
    criteria: list[dict] = []
    for spec in specs:
        missing = [f for f in _REQUIRED_SPEC_FIELDS if f not in spec]
        if missing:
            raise CriteriaError(f"criterion spec missing field(s): {missing!r} in {spec!r}")
        cid = spec["id"]
        if cid in seen_ids:
            raise CriteriaError(f"duplicate criterion id: {cid!r}")
        seen_ids.add(cid)
        # "status": FAILING is set here, at construction, inside the dict
        # literal -- not via a follow-up assignment -- so this does not
        # count as a second mutation site. Any "status" in the incoming
        # spec is deliberately not read.
        criteria.append({
            "id": cid,
            "description": spec["description"],
            "oracle": spec["oracle"],
            "status": FAILING,
            "evidence": None,
        })
    return criteria


def apply_oracle_result(criteria: list[dict], criterion_id: str, oracle: str,
                         ok: bool, evidence=None) -> dict:
    """Flip one criterion's status -- the only function in this module that does.

    Raises CriteriaError if criterion_id is unknown, or if `oracle` does not
    match the oracle name registered on that criterion (the wrong oracle
    cannot vouch for a criterion it was never named for). Returns the flip
    record. A False result flips PASSING back to FAILING just as readily as
    a True one flips FAILING to PASSING -- a regression is not sticky.
    """
    for c in criteria:
        if c["id"] == criterion_id:
            if c["oracle"] != oracle:
                raise CriteriaError(
                    f"oracle {oracle!r} is not registered for criterion "
                    f"{criterion_id!r} (registered: {c['oracle']!r})")
            before = c["status"]
            after = PASSING if ok else FAILING
            c["status"] = after  # the ONE mutation site; see module docstring
            c["evidence"] = evidence
            return {
                "criterion_id": criterion_id,
                "oracle": oracle,
                "from": before,
                "to": after,
                "evidence": evidence,
            }
    raise CriteriaError(f"unknown criterion id: {criterion_id!r}")


def all_pass(criteria: list[dict]) -> bool:
    # Operand order (constant, then lookup) keeps this comparison a read, not
    # a pattern the source-grep test below would mistake for an assignment.
    return all(PASSING == c["status"] for c in criteria)


def failing(criteria: list[dict]) -> list[str]:
    return [c["id"] for c in criteria if c["status"] != PASSING]


def summary(criteria: list[dict]) -> dict:
    fail_ids = failing(criteria)
    return {
        "total": len(criteria),
        "passing": len(criteria) - len(fail_ids),
        "failing_ids": fail_ids,
        "all_pass": len(fail_ids) == 0,
    }


def does_not_prove() -> list[str]:
    """What a fully-PASSING criteria set does NOT establish."""
    return [
        "NOT_PROVES_TASK_DONE",       # named oracles satisfied != the task is right
        "NOT_PROVES_ORACLE_QUALITY",  # a criterion is only as strong as its oracle
    ]
