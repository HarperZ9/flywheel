"""contract_stage.py -- the output contract as a stage the loop can run.

`run_loop` verifies that a candidate satisfies its oracle. That is a different
question from whether the values inside the candidate agree with the sources
that decide them, and the tax case is the whole argument for asking both: an
answer can pass every test it was given and still charge the wrong tax, because
nothing in the test asked which table governs.

This module is the seam. It pulls an answer out of a candidate, checks it
against the contract, writes the result to the ledger so the goal and session
scopes can read it later, and hands back a report. It gates nothing on its own.
The loop decides what a HOLD means, and the caller decides what a lane does
with a held answer.

An unparsable candidate is not an error here. It becomes an empty answer, every
contract field reports absent, and the critical ones hold. That is the same
outcome the honest path produces, reached without a special case.
"""
from __future__ import annotations

import json

from .contract_terms import AGREES, HOLD
from .output_contract import check_answer
from .validation_ledger import TASK, record

_FENCE = "```"


def answer_from(candidate) -> dict:
    """The answer object inside a candidate, or an empty one.

    Accepts a dict as-is, a JSON object, or a JSON object inside a fenced
    block, because a model asked for JSON returns all three.
    """
    if isinstance(candidate, dict):
        return candidate
    text = (candidate or "").strip() if isinstance(candidate, str) else ""
    if not text:
        return {}
    if _FENCE in text:
        parts = text.split(_FENCE)
        for part in parts[1:]:
            body = part.split("\n", 1)[-1] if part[:1].isalpha() else part
            found = _loads(body)
            if found:
                return found
    return _loads(text)


def _loads(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_output(candidate, contract: list[dict], authorities: dict, *,
                    scope: str = TASK, subject: str = "",
                    ledger=None, extract=None, write: bool = True) -> dict:
    """Check a candidate against its contract and append the result.

    `extract` overrides how the answer is pulled out, for a lane whose output
    is not JSON. `write=False` runs the check without touching the ledger,
    which is what a dry run wants.
    """
    answer = (extract or answer_from)(candidate) or {}
    report = check_answer(answer, contract, authorities or {})
    if write:
        record(report, scope=scope, subject=subject, path=ledger)
    return report


def holds(report: dict) -> bool:
    """Whether this report stops the answer. The only question the loop asks."""
    return report.get("release") == HOLD


def stage_payload(report: dict) -> dict:
    """The part of a report that belongs in a chain receipt.

    The field rows without their prose. A receipt records what was decided;
    the reasons are in the report the caller already holds, and copying them
    into the chain doubles the size of every envelope for no re-checkable gain.
    """
    return {
        "release": report.get("release", ""),
        "blocking": list(report.get("blocking", [])),
        "checked": report.get("checked", 0),
        "passed": report.get("passed", 0),
        "unresolved": list(report.get("unresolved", [])),
        "codes": {row["field"]: row["code"]
                  for row in report.get("fields", [])
                  if row["code"] != AGREES},
    }
