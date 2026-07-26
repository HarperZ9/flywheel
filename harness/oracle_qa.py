"""oracle_qa.py -- attack the verifier before trusting its verdicts as rewards.

A verifier whose false accepts have never been measured is a reward function of
unknown correctness, and training on it teaches whatever it happens to be wrong
about. So a checker earns an OracleQACard before the registry will treat its
verdicts as reward-eligible, and a missing card means not eligible.

Two disciplines, both about not overstating thin evidence:

  1. **No bare zero.** Zero false accepts out of three mutants proves almost
     nothing, so the card reports a Wilson UPPER BOUND at a declared confidence.
     "0 false accepts" becomes "at most 0.60 at 95% confidence, n=3", and the
     weakness of the evidence is visible on the face of the claim rather than
     hidden behind a reassuring integer.
  2. **Required n per class.** A battery that ran one mutant per class has
     bounded almost nothing. Below the floor the card does not pass, and says
     INSUFFICIENT_N.

The card states its own limit: this bounds only the mutations we imagined. It
quantifies the sample, never the imagination. A real exploit outside the classes
below would pass silently, and the honest response to that is to keep adding
classes as they are discovered rather than to claim the list is complete.

TYPE_CONFUSION exists because of a real find: bool subclasses int in Python, so
`[[true, 0]]` was accepted with True read as row 1 until Task 6 closed it. That
mutation is now a permanent regression probe.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from dataclasses import dataclass, field

from .qa_mutations import MutationClass, QAError, mutate
from .verdict import Verdict

REQUIRED_N_PER_CLASS = 3
DEFAULT_COUNT_PER_CLASS = 6
DEFAULT_CONFIDENCE = 0.95
SCHEMA = "flywheel.oracle-qa-card/v1"

# Two-sided normal quantiles for the confidences we support. Hard-coded rather
# than computed so the stdlib-only constraint holds and the numbers are auditable.
_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054,
      0.99: 2.5758293035489004}


def wilson_upper_bound(successes: int, n: int,
                       confidence: float = DEFAULT_CONFIDENCE) -> float:
    """Upper end of the Wilson score interval for a binomial proportion.

    Chosen over the normal approximation because it stays inside [0, 1] and
    behaves at the boundary, which is exactly where this measurement lives: the
    interesting case is zero observed false accepts, where the naive estimate is
    0.0 and the honest answer is "we cannot rule out a lot".
    """
    if n <= 0:
        raise QAError("a bound needs at least one trial")
    if successes < 0 or successes > n:
        raise QAError(f"{successes} successes out of {n} trials is impossible")
    z = _Z.get(round(confidence, 2))
    if z is None:
        raise QAError(f"unsupported confidence {confidence}; "
                      f"choose one of {sorted(_Z)}")
    p = successes / n
    denom = 1.0 + (z * z) / n
    centre = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return min(1.0, (centre + margin) / denom)


@dataclass
class OracleQACard:
    schema: str
    oracle_type: str
    family: str
    checker_source_sha256: str
    n_valid: int
    n_mutants: int
    false_accepts: int
    false_rejects: int
    unverifiable_seen: int
    false_accept_upper_bound: float
    confidence: float
    required_n_per_class: int
    per_class: dict
    failures: list[str] = field(default_factory=list)
    does_not_prove: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "schema": self.schema, "oracle_type": self.oracle_type,
            "family": self.family,
            "checker_source_sha256": self.checker_source_sha256,
            "n_valid": self.n_valid, "n_mutants": self.n_mutants,
            "false_accepts": self.false_accepts,
            "false_rejects": self.false_rejects,
            "unverifiable_seen": self.unverifiable_seen,
            "false_accept_upper_bound": f"{self.false_accept_upper_bound:.6f}",
            "confidence": self.confidence,
            "required_n_per_class": self.required_n_per_class,
            "per_class": self.per_class,
            "passed": self.passed,
            "failures": sorted(self.failures),
            "does_not_prove": self.does_not_prove,
        }

    def card_hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


def qa_battery(oracle, valid_certs: list[str], *, seed: int = 0,
               count_per_class: int = DEFAULT_COUNT_PER_CLASS,
               confidence: float = DEFAULT_CONFIDENCE) -> OracleQACard:
    """Attack `oracle` and return its card. A card is not a pass by itself: read
    `passed`, and read the bound even when it passed."""
    if not valid_certs:
        raise QAError(
            "a battery needs at least one known-valid certificate, or a checker "
            "that rejects everything would score perfectly")

    failures: set[str] = set()
    try:
        source_sha = hashlib.sha256(
            inspect.getsource(type(oracle)).encode()).hexdigest()
    except (OSError, TypeError):
        # A class defined in a REPL or an exec'd string has no retrievable
        # source. Do not crash, and do not quietly pass either: a card that
        # cannot pin the code it graded could be reused after an edit, so the
        # card is marked instead.
        source_sha = ""
        failures.add("SOURCE_UNPINNED")

    false_rejects = 0
    unverifiable_seen = 0
    for cert in valid_certs:
        v = oracle.verify(cert, None).verdict()
        if v == Verdict.UNVERIFIABLE.value:
            # Not a rejection of the candidate. Counting it as a false reject
            # would punish a checker for honestly declaring its scope.
            unverifiable_seen += 1
        elif v != Verdict.PASS.value:
            false_rejects += 1
    if false_rejects:
        failures.add("FALSE_REJECT")

    per_class: dict = {}
    total_mutants = 0
    false_accepts = 0
    for cls in MutationClass:
        muts: list[str] = []
        for cert in valid_certs:
            muts.extend(mutate(cert, cls, count=count_per_class, seed=seed))
        accepted = 0
        for mtext in muts:
            if oracle.verify(mtext, None).verdict() == Verdict.PASS.value:
                accepted += 1
        # A class that produced NOTHING is not applicable to this family (a
        # graph-shaped mutation against a tensor certificate, say). That is
        # different from a class that ran too few mutants, and conflating them
        # made every non-graph family fail INSUFFICIENT_N forever, which is how a
        # gate stops being a gate and becomes a wall.
        applicable = len(muts) > 0
        per_class[cls.value] = {"n": len(muts), "accepted": accepted,
                                "applicable": applicable}
        total_mutants += len(muts)
        false_accepts += accepted
        if applicable and len(muts) < REQUIRED_N_PER_CLASS:
            failures.add("INSUFFICIENT_N")
    if not any(v["applicable"] for v in per_class.values()):
        failures.add("NO_APPLICABLE_MUTATIONS")

    if false_accepts:
        failures.add("FALSE_ACCEPT")

    bound = wilson_upper_bound(false_accepts, max(total_mutants, 1),
                               confidence=confidence)

    return OracleQACard(
        schema=SCHEMA,
        oracle_type=getattr(oracle, "oracle_type", type(oracle).__name__),
        family=getattr(oracle, "family", "unset"),
        checker_source_sha256=source_sha,
        n_valid=len(valid_certs), n_mutants=total_mutants,
        false_accepts=false_accepts, false_rejects=false_rejects,
        unverifiable_seen=unverifiable_seen,
        false_accept_upper_bound=bound, confidence=confidence,
        required_n_per_class=REQUIRED_N_PER_CLASS,
        per_class=per_class, failures=sorted(failures),
        does_not_prove=[
            "NOT_PROVES_ABSENCE_OF_UNIMAGINED_EXPLOITS: this battery bounds only "
            "the mutation classes enumerated here. It quantifies the sample, "
            "never the imagination.",
            "NOT_PROVES_CORRECTNESS_OF_THE_PREDICATE: a checker can be sound "
            "against every mutant and still implement the wrong mathematics.",
        ])
