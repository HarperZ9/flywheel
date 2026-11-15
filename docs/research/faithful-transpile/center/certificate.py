"""Certificate — the witnessed verdict, NAMING the criterion it was judged against.

Shaped to the coherence-membrane Certificate contract (claim, verdict, oracle, evidence) so it can be
reused/lifted into the spine later, extended with the two things this layer adds: the `criterion` it was
judged against (name + weights) and the per-candidate `scores`. Verdicts ride the three-valued lattice.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    VERIFIED = "verified"        # a winner was decided under the named criterion
    REFUTED = "refuted"          # reserved (a candidate that fails the criterion outright)
    UNVERIFIABLE = "unverifiable"  # no criterion / no candidates / undecidable — fail-closed


@dataclass(frozen=True)
class Certificate:
    claim: str
    verdict: Verdict
    oracle: str                                  # versioned id of what produced this verdict
    criterion: dict = field(default_factory=dict)   # {name, dims} — the named criterion (or {} if none)
    scores: dict = field(default_factory=dict)      # candidate -> {dim: score, "weighted": float}
    winner: str | None = None
    evidence: tuple = ()                            # ordered (key, value) pairs

    def to_dict(self) -> dict:
        return {"claim": self.claim, "verdict": self.verdict.value, "oracle": self.oracle,
                "criterion": self.criterion, "scores": self.scores, "winner": self.winner,
                "evidence": [list(p) for p in self.evidence]}

    @classmethod
    def from_dict(cls, d: dict) -> "Certificate":
        return cls(claim=d["claim"], verdict=Verdict(d["verdict"]), oracle=d["oracle"],
                   criterion=d.get("criterion", {}), scores=d.get("scores", {}),
                   winner=d.get("winner"), evidence=tuple(tuple(p) for p in d.get("evidence", ())))
