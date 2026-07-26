"""verdict.py -- the shared verdict vocabulary.

Four verdicts, not two. A boolean cannot say "the oracle decided it cannot
decide", and a system whose interface cannot carry UNVERIFIABLE cannot honestly
claim UNVERIFIABLE is first class. The gap is part of the record.

Attribution is separate from the verdict because who caused a non-completion
decides whether it teaches anything. A candidate that loops forever earned its
FAIL. A missing toolchain did not, and training on it would teach the model that
our environment's absence is its error.
"""
from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNDECIDED = "UNDECIDED"          # the oracle ran and declined to dispose
    UNVERIFIABLE = "UNVERIFIABLE"    # the oracle could not run at all


class Execution(str, Enum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    CRASHED = "CRASHED"
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"
    TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
    HARNESS_ERROR = "HARNESS_ERROR"


class Attribution(str, Enum):
    CANDIDATE = "CANDIDATE"
    HARNESS = "HARNESS"
    ENVIRONMENT = "ENVIRONMENT"


class UndecidedReason(str, Enum):
    HELD_OUT_DISAGREEMENT = "HELD_OUT_DISAGREEMENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NON_CONJUNCTIVE_RULE = "NON_CONJUNCTIVE_RULE"
    CONSENSUS_NOT_PROOF = "CONSENSUS_NOT_PROOF"
    RECEIPT_COMMIT_FAILED = "RECEIPT_COMMIT_FAILED"


class UnverifiableReason(str, Enum):
    """Why no verdict could be reached. A bare UNVERIFIABLE is unactionable and
    indistinguishable from "we did not look", so the reason is mandatory.

    OUT_OF_SCOPE is the pre-dispatch envelope rejection: the instance's declared
    parameters sit outside the criterion's domain of applicability, so the check
    was never run. Distinct from UndecidedReason.OUT_OF_SCOPE, which is an oracle
    that ran and then found the case beyond what it can dispose.
    """
    ORACLE_UNAVAILABLE = "ORACLE_UNAVAILABLE"
    TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
    QA_CARD_ABSENT = "QA_CARD_ABSENT"
    ENVELOPE_MISSING = "ENVELOPE_MISSING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CONFOUNDED = "CONFOUNDED"


_CANDIDATE_EXECUTIONS = {
    Execution.COMPLETED,
    Execution.TIMEOUT,
    Execution.CRASHED,
    Execution.RESOURCE_EXCEEDED,
}

_ATTRIBUTION = {
    Execution.HARNESS_ERROR: Attribution.HARNESS,
    Execution.TOOLCHAIN_MISSING: Attribution.ENVIRONMENT,
}


def is_dispositive(verdict: Verdict | str) -> bool:
    """True iff the verdict decided the question. Only PASS and FAIL do."""
    return Verdict(verdict) in (Verdict.PASS, Verdict.FAIL)


def attribution_for(execution: Execution | str) -> Attribution:
    """Who caused this non-completion. Candidate-attributable failures are real
    FAILs and carry gradient; harness and environment failures are dropped and
    logged, never scored."""
    ex = Execution(execution)
    if ex in _CANDIDATE_EXECUTIONS:
        return Attribution.CANDIDATE
    return _ATTRIBUTION[ex]
