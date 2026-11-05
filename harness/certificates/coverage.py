"""coverage.py -- what a certificate check covered, and where its guarantee stops.

Split from base.py so the coverage record and its stop reasons have one home.
`SPENT` names the stop reasons that mean the check ran out before it finished;
the base turns a valid result with one of them into UNDECIDED with
BUDGET_EXHAUSTED.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Stop reasons that mean the check ran out before it finished.
SPENT = frozenset({"budget", "timeout"})


class CertificateError(ValueError):
    """A malformed coverage claim or checker contract."""


@dataclass(frozen=True)
class Coverage:
    """What the check actually covered, and where its guarantee stops."""
    predicate_exact: bool
    search_space_enumerated: bool
    enumerated_fraction: str            # decimal or rational STRING, never float
    stop_reason: str                    # complete | budget | timeout | bound
    guarantee_weakens_above: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enumerated_fraction, str):
            raise CertificateError(
                "enumerated_fraction must be a string (a float in a hashed field "
                "makes a stranger's replay disagree over formatting)")

    def to_dict(self) -> dict:
        return asdict(self)
