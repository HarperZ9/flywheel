"""CriterionSpec — the human's named, weighted criterion (the one role §6 says cannot be delegated).

A criterion is a readout the human cares to preserve, named and weighted across dimensions. It is
EXTERNAL to the minds being reconciled; the center hosts whichever is named (criterion-relativity is
the point). Normalized so a stance is a stance, not a thumb on the scale by accident.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CriterionSpec:
    name: str
    dims: dict[str, float]   # dimension -> weight (will be normalized to sum 1)

    def __post_init__(self):
        if not self.name or not str(self.name).strip():
            raise ValueError("criterion must be named (the human owns it)")
        if not self.dims:
            raise ValueError("criterion needs at least one weighted dimension")
        if any(w < 0 for w in self.dims.values()):
            raise ValueError("criterion weights must be non-negative")
        if sum(self.dims.values()) <= 0:
            raise ValueError("criterion weights must sum to a positive value")

    def normalized(self) -> "CriterionSpec":
        total = sum(self.dims.values())
        return CriterionSpec(self.name, {d: w / total for d, w in self.dims.items()})

    def score(self, dim_scores: dict[str, float]) -> float:
        """Weighted sum of a candidate's per-dimension scores under this (normalized) criterion.
        Dimensions absent from the candidate score 0 — an unmeasured dimension is not free credit."""
        w = self.normalized().dims
        return round(sum(weight * float(dim_scores.get(dim, 0.0)) for dim, weight in w.items()), 6)

    @classmethod
    def from_dict(cls, d: dict) -> "CriterionSpec":
        return cls(name=d["name"], dims={k: float(v) for k, v in d["dims"].items()})

    def to_dict(self) -> dict:
        return {"name": self.name, "dims": self.normalized().dims}
