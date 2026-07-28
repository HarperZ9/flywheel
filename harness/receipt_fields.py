"""receipt_fields.py -- the field types a receipt is built from, and their rules.

Split out of receipt.py when that module crossed the 300-line gate. The boundary
is real rather than cosmetic: this module defines what a field IS and refuses
malformed ones, while receipt.py composes fields into a claim and digests it.
Either can be replaced without touching the other.

Three rules live here because they are properties of the fields themselves:

  - NOMINAL vocabularies have no order, and the ordering operators are explicitly
    removed. Inheriting from str is convenient for JSON and silently supplies `<`
    via ALPHABETICAL comparison, which is worse than being ordered on purpose:
    somebody sorts by evidence kind, gets a ranking that looks meaningful, and it
    is really just the alphabet.
  - NO FLOATS in anything destined for a hash. Cross-platform float formatting is
    the likeliest way an honest stranger's replay disagrees over nothing real.
  - A DENOMINATOR is mandatory and self-consistent. A hit count without attempts
    is unpriceable: a generator firing a million shots looks identical to one
    firing ten.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from enum import Enum


class ReceiptError(ValueError):
    """A receipt that could not be re-derived, or could be re-derived two ways."""


class _NominalEnum(str, Enum):
    """A closed vocabulary with NO ordering.

    Ordering evidence kinds would floor human judgement beneath machine checking
    and make pruning the input closure the rational move, so comparison raises
    instead of ranking. Equality, hashing, and dict or set use still work, which
    is what JSON and lookups actually need.
    """

    def compare_to(self, other) -> None:
        raise ReceiptError(
            f"{type(self).__name__} is NOMINAL: comparing {self.value} to "
            f"{getattr(other, 'value', other)} is a validation error. Ordering "
            "evidence kinds would floor human judgement beneath machine "
            "checking and reward pruning the input closure.")

    def _refuse_ordering(self, other):
        raise TypeError(
            f"{type(self).__name__} is nominal and has no order. str comparison "
            f"would rank {self.value!r} against {getattr(other, 'value', other)!r} "
            "alphabetically, which means nothing. Use compare_to() for the "
            "explanation, or stop comparing.")

    __lt__ = _refuse_ordering
    __le__ = _refuse_ordering
    __gt__ = _refuse_ordering
    __ge__ = _refuse_ordering


class EvidenceKind(_NominalEnum):
    FORMAL = "FORMAL"
    CONSTRUCTIVE = "CONSTRUCTIVE"
    COMPUTATIONAL = "COMPUTATIONAL"
    EMPIRICAL = "EMPIRICAL"
    ADJUDICATED = "ADJUDICATED"


class Tier(_NominalEnum):
    PROOF_CHECKER = "proof_checker"
    CONSTRUCTION_CERTIFICATE = "construction_certificate"
    EXACT_SYMBOLIC = "exact_symbolic"
    NUMERIC_SYMBOLIC = "numeric_symbolic"
    EXECUTION_TEST = "execution_test"
    SIMULATION = "simulation"
    HUMAN_ENDPOINT = "human_endpoint"
    WET_LAB = "wet_lab"


_COUNTS = ("attempts", "group_size", "oracle_calls_consumed", "hits",
           "undecided", "unverifiable", "parse_failures", "timeouts",
           "tokens_in", "tokens_out", "cache_hit_tokens",
           "tasks_proposed", "tasks_filtered_out", "retries")


@dataclass(frozen=True)
class Denominator:
    """Without these a hit count means nothing. No defaults on the counts: a
    missing denominator must be a hard error rather than a silent zero."""
    attempts: int
    group_size: int
    oracle_calls_consumed: int
    hits: int
    undecided: int
    unverifiable: int
    parse_failures: int
    timeouts: int
    tokens_in: int
    tokens_out: int
    cache_hit_tokens: int
    tasks_proposed: int
    tasks_filtered_out: int
    retries: int
    # Did the proposer see oracle output between attempts? A hit found with the
    # checker's own feedback in the loop is a different quantity from one found
    # blind, and the difference is invisible unless it is recorded.
    oracle_feedback_visible: bool
    filter_id: str
    filter_hash: str
    filter_is_learned: bool

    def __post_init__(self) -> None:
        for name in _COUNTS:
            v = getattr(self, name)
            # bool is an int in Python; a bool count is a type error here.
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ReceiptError(f"{name} must be a non-negative integer")
        if not isinstance(self.oracle_feedback_visible, bool):
            raise ReceiptError("oracle_feedback_visible must be a bool")
        if self.hits > self.attempts:
            raise ReceiptError(
                f"{self.hits} hits out of {self.attempts} attempts is impossible")
        if not self.filter_id or not self.filter_hash:
            raise ReceiptError(
                "a task filter must be identified and hashed, or the population "
                "the receipt was drawn from is unknowable")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Budget:
    """The CEILING a run was allowed. This is not what it consumed.

    Consumption lives in Denominator, and neither field substitutes for the
    other. A FAIL reached with headroom to spare and a FAIL that stopped at the
    limit are different results, and only the ceiling tells them apart.

    `declared` exists so that "no budget" cannot be spelled as a zero. An
    undeclared budget is a stated absence, which `does_not_prove` reports, rather
    than three zeros that read as a run permitted nothing at all.
    """
    wall_seconds_limit: int
    tokens_limit: int
    retries_limit: int
    exhausted: bool
    declared: bool = True

    _LIMITS = ("wall_seconds_limit", "tokens_limit", "retries_limit")

    def __post_init__(self) -> None:
        for name in self._LIMITS:
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ReceiptError(f"{name} must be a non-negative integer")
        for name in ("exhausted", "declared"):
            if not isinstance(getattr(self, name), bool):
                raise ReceiptError(f"{name} must be a bool")
        if not self.declared:
            if any(getattr(self, n) for n in self._LIMITS):
                raise ReceiptError(
                    "an undeclared budget carries no limits, and a limit that is "
                    "set is declared by definition")
            if self.exhausted:
                raise ReceiptError("an undeclared budget cannot be exhausted")

    @classmethod
    def undeclared(cls) -> "Budget":
        """No ceiling was recorded. Say so explicitly rather than passing zeros."""
        return cls(0, 0, 0, exhausted=False, declared=False)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GradedScore:
    """A grading oracle's score as an EXACT rational in [0,1], with its trials.

    Three refusals, each for a reason already load-bearing elsewhere in this
    module. Never a float, because cross-platform float text is how an honest
    replay disagrees over nothing real. Never a replacement for the four-way
    verdict: a receipt carries both, so a score of nine tenths cannot quietly
    become a PASS. And never a score without its trial count, for the same reason
    a hit count without attempts is unpriceable.
    """
    numerator: int
    denominator: int
    trials: int
    grader_id: str
    grader_sha256: str

    def __post_init__(self) -> None:
        for name in ("numerator", "denominator", "trials"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ReceiptError(f"{name} must be a non-negative integer")
        if self.denominator == 0:
            raise ReceiptError(
                "a graded score needs a nonzero denominator, or the score is not "
                "a number")
        if self.numerator > self.denominator:
            raise ReceiptError(
                f"{self.numerator}/{self.denominator} falls outside [0,1]")
        if self.trials < 1:
            raise ReceiptError("a graded score needs at least one trial")
        if not self.grader_id or not self.grader_sha256:
            raise ReceiptError(
                "a grader must be identified and hashed, or its score cannot be "
                "reproduced")

    def as_decimal_string(self, places: int = 6) -> str:
        """Display only, derived from the integers by integer arithmetic. The
        hashed form is always the rational, never this."""
        if places < 1:
            raise ReceiptError("places must be at least 1")
        scale = 10 ** places
        scaled = self.numerator * scale // self.denominator
        return f"{scaled // scale}.{scaled % scale:0{places}d}"

    def to_dict(self) -> dict:
        return asdict(self)


def no_floats(value, where: str) -> None:
    """Walk a structure and refuse any float. Bools pass: they are not numbers
    whose text form varies across platforms."""
    if isinstance(value, float):
        raise ReceiptError(
            f"{where} contains a float ({value!r}). Hashed fields carry integers "
            "or decimal strings, because cross-platform float formatting is how "
            "an honest replay disagrees over nothing real.")
    if isinstance(value, dict):
        for k, v in value.items():
            no_floats(v, f"{where}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            no_floats(v, f"{where}[{i}]")


def canonical(obj) -> str:
    """Canonical JSON: sorted keys, tight separators, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
