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
from pathlib import Path

from .contract_terms import AGREES, HOLD
from .output_contract import check_answer
from .proof_lean import lean_source
from .proof_relations import RelationError
from .proof_run import prove
from .validation_ledger import TASK, record
from .verdict import Verdict

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


def _unverified(reason: str, **extra) -> dict:
    return dict({"verdict": Verdict.UNVERIFIABLE.value, "checker": "",
                 "axioms": [], "errors": [], "reason": reason}, **extra)


def emit_proof(report: dict, answer: dict, contract: list[dict], path=None, *,
               relations=(), verify: bool = False) -> dict:
    """The same check as a Lean file, and the kernel's reading of it.

    A relation the contract states and the emitter will not read comes back
    unverified rather than failing the answer. That is an authoring error in
    the contract, and holding a lane's answer over it would report a defect in
    the document as a defect in the work.
    """
    try:
        body = lean_source(report, answer, contract, relations=relations or ())
    except RelationError as exc:
        return _unverified(f"the contract states a relation this module will "
                           f"not read: {exc}")
    if verify:
        return prove(body, path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(body, encoding="utf-8")
    return _unverified("written, not checked", file=str(path))


def validate_output(candidate, contract: list[dict], authorities: dict, *,
                    scope: str = TASK, subject: str = "",
                    ledger=None, extract=None, write: bool = True,
                    proof=None, relations=(), verify_proof: bool = False) -> dict:
    """Check a candidate against its contract and append the result.

    `extract` overrides how the answer is pulled out, for a lane whose output
    is not JSON. `write=False` runs the check without touching the ledger,
    which is what a dry run wants.

    `proof` names where the Lean file goes and `verify_proof` runs the kernel
    on it. Running Lean means running a program, so a lane asks for it the same
    way it asks for a command authority.
    """
    answer = (extract or answer_from)(candidate) or {}
    report = check_answer(answer, contract, authorities or {})
    if proof or verify_proof:
        report["proof"] = emit_proof(report, answer, contract, proof,
                                     relations=relations, verify=verify_proof)
    if write:
        record(report, scope=scope, subject=subject, path=ledger)
    return report


def holds(report: dict) -> bool:
    """Whether this report stops the answer. The only question the loop asks."""
    if report.get("proof", {}).get("verdict") == Verdict.FAIL.value:
        # Two readings of one answer, built from different code, and the kernel
        # refused an obligation the check passed. One of them is wrong, and a
        # lane does not accept while that is open. A proof nobody could run is
        # unverified rather than refused, and does not reach here.
        return True
    return report.get("release") == HOLD


def stage_payload(report: dict) -> dict:
    """The part of a report that belongs in a chain receipt.

    The field rows without their prose. A receipt records what was decided;
    the reasons are in the report the caller already holds, and copying them
    into the chain doubles the size of every envelope for no re-checkable gain.
    """
    payload = {
        "release": report.get("release", ""),
        "blocking": list(report.get("blocking", [])),
        "checked": report.get("checked", 0),
        "passed": report.get("passed", 0),
        "unresolved": list(report.get("unresolved", [])),
        "codes": {row["field"]: row["code"]
                  for row in report.get("fields", [])
                  if row["code"] != AGREES},
    }
    proof = report.get("proof")
    if proof:
        # The axiom list is the trust surface by name, which is the part of a
        # proof a later reader can act on. The prose stays in the report.
        payload["proof"] = {"verdict": proof["verdict"],
                            "checker": proof.get("checker", ""),
                            "axioms": list(proof.get("axioms", []))}
    return payload
