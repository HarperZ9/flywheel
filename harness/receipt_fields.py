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
           "tasks_proposed", "tasks_filtered_out")


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
    filter_id: str
    filter_hash: str
    filter_is_learned: bool

    def __post_init__(self) -> None:
        for name in _COUNTS:
            v = getattr(self, name)
            # bool is an int in Python; a bool count is a type error here.
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ReceiptError(f"{name} must be a non-negative integer")
        if self.hits > self.attempts:
            raise ReceiptError(
                f"{self.hits} hits out of {self.attempts} attempts is impossible")
        if not self.filter_id or not self.filter_hash:
            raise ReceiptError(
                "a task filter must be identified and hashed, or the population "
                "the receipt was drawn from is unknowable")

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
