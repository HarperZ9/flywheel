"""validated_answer.py -- produce, check against the authority, retry, then emit.

The loop `output_contract` was written for. An answer is produced, checked
against the sources that decide its fields, and on anything short of PASS the
unresolved fields go back to the producer as structured data rather than as
criticism. Nothing is emitted as finished until it has been checked, and an
answer that never validates is still returned, carrying the reason.

Two stop conditions, not one. Attempts run out, or the same failure signature
comes back a second time. A retry that reproduces a failure it already produced
is a reroll, and spending three more provider calls on it buys a costlier way
to be wrong.

What this does not do: it does not make an answer correct, and a contract with
a lenient authority validates a bad answer exactly as fast as a good one. The
authority is where the rigor lives. This only guarantees one was consulted.
"""
from __future__ import annotations

from .contract_feedback import feedback
from .output_contract import check_answer
from .verdict import Verdict

SCHEMA = "flywheel.validated-answer/v1"

VALIDATED = "validated"
ATTEMPTS_EXHAUSTED = "attempts_exhausted"
NO_PROGRESS = "no_progress"


class ValidationError(ValueError):
    """Raised on a loop that could not validate anything by construction."""


def _signature(report: dict) -> tuple:
    """What went wrong, with the prose dropped.

    A signature the loop has already produced means this attempt landed
    somewhere it has been. Held as a set rather than as the previous value, so
    an answer oscillating between two wrong shapes is caught too.
    """
    return tuple(sorted((row["field"], row["verdict"], row["code"])
                        for row in report["fields"]
                        if row["verdict"] != Verdict.PASS.value))


def run_validated(produce, contract: list[dict], authorities: dict,
                  *, max_attempts: int = 3) -> dict:
    """Run `produce` until its answer validates, it stops improving, or attempts
    run out. `produce(feedback)` receives None on the first attempt and the
    previous report's feedback on every attempt after it.
    """
    if max_attempts < 1:
        raise ValidationError("a loop that never produces an answer cannot validate one")
    reports: list[dict] = []
    seen: set[tuple] = set()
    hint = None
    halted = ATTEMPTS_EXHAUSTED
    answer = None
    report: dict = {}
    for _ in range(max_attempts):
        answer = produce(hint)
        report = check_answer(answer, contract, authorities)
        reports.append(report)
        if report["verdict"] == Verdict.PASS.value:
            halted = VALIDATED
            break
        signature = _signature(report)
        if signature in seen:
            halted = NO_PROGRESS
            break
        seen.add(signature)
        hint = feedback(report)
    return {
        "schema": SCHEMA,
        "verdict": report["verdict"],
        "halted": halted,
        "emit": report["verdict"] == Verdict.PASS.value,
        "attempts": len(reports),
        "unresolved": list(report["unresolved"]),
        "answer": answer,
        "reports": reports,
    }


_NOTICE = {
    Verdict.FAIL.value: "This answer disagrees with the source that decides it "
                        "on {fields}. Read it as a draft.",
    Verdict.UNVERIFIABLE.value: "Nothing confirmed {fields} in this answer, so "
                                "it is unchecked rather than wrong.",
}


def emission(result: dict) -> dict:
    """The answer as a reader should receive it.

    A validated answer travels alone. An unvalidated one travels with the
    reason, because the failure this module exists for is not a wrong answer.
    It is a wrong answer that arrived looking finished.
    """
    verdict = result["verdict"]
    if verdict == Verdict.PASS.value:
        return {"answer": result["answer"], "verdict": verdict,
                "unresolved": [], "notice": ""}
    fields = ", ".join(result["unresolved"]) or "this answer"
    return {"answer": result["answer"], "verdict": verdict,
            "unresolved": list(result["unresolved"]),
            "notice": _NOTICE[verdict].format(fields=fields)}
