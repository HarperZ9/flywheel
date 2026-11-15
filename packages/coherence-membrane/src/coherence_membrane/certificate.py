"""Certificate -- a witnessed verdict + its evidence (the verifier layer's keystone).

A claim's truth is never a token; it is a Certificate carrying a deductive verdict
and the evidence for it. Verdicts map onto the three-valued lattice
(VERIFIED/REFUTED/UNVERIFIABLE <-> MATCH/DRIFT/UNVERIFIABLE)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    VERIFIED = "verified"
    REFUTED = "refuted"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class Certificate:
    """A checkable verdict about a claim.

    claim    -- the statement that was checked (human-readable).
    verdict  -- VERIFIED / REFUTED / UNVERIFIABLE.
    oracle   -- versioned oracle id (tool self-provenance), e.g. "propositional-dpll-v1".
    evidence -- ordered key->value pairs (counterexample, unsat marker, or reason);
               tuple-of-pairs keeps it frozen + deterministically serialisable.
    """

    claim: str
    verdict: Verdict
    oracle: str
    evidence: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "oracle": self.oracle,
            "evidence": [list(p) for p in self.evidence],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Certificate":
        """Inverse of to_dict -- round-trips the proof token from its wire form.

        Symmetric: from_dict(c.to_dict()) == c. Raises ValueError on an unknown
        verdict string (fail-closed: an off-lattice value is rejected, not coerced)."""
        return cls(
            claim=d["claim"],
            verdict=Verdict(d["verdict"]),
            oracle=d["oracle"],
            evidence=tuple(tuple(p) for p in d.get("evidence", ())),
        )
