"""Judge — the EXTERNAL witness. Scores a candidate's per-dimension faithfulness to the subject.

Per the principle, faithfulness cannot be certified from inside; the judge is external to the minds.
v1 ships the interface + a deterministic StubJudge whose scores are a property of the candidate text
(so tests are hermetic and criterion-relativity is reproducible). The real judge is a model, later,
behind this same interface.
"""
from __future__ import annotations
from typing import Protocol

DIMENSIONS = ("novelty", "structure", "function", "completeness", "grounded")


class Judge(Protocol):
    def score(self, candidate: str, subject_views: dict[str, str], dims: tuple[str, ...]) -> dict[str, float]:
        ...


class StubJudge:
    """Deterministic per-dimension scorer for hermetic tests. Scores are derived from the candidate's
    shape so the three candidate kinds separate the way the live demo found:
      - a single-channel SOLO scores high on its channel's strength + novelty, low on completeness;
      - the RECONCILED meeting scores high on structure/function/completeness, lower on novelty.
    This is a stand-in for a real witness, not a measurement; the loop logic it exercises is real.
    """

    def score(self, candidate: str, subject_views, dims=DIMENSIONS) -> dict[str, float]:
        c = candidate.lower()
        if "reconciled" in c:                    # the meeting: whole, grounded, not novel
            base = {"novelty": 0.40, "structure": 0.95, "function": 0.95,
                    "completeness": 0.95, "grounded": 0.85}
        elif "[text]" in c:                       # text solo: function + novelty, weak structure
            base = {"novelty": 0.90, "structure": 0.30, "function": 0.90,
                    "completeness": 0.40, "grounded": 0.90}
        else:                                     # other channel (e.g. diagram): structure, weak function
            base = {"novelty": 0.90, "structure": 0.90, "function": 0.20,
                    "completeness": 0.40, "grounded": 0.92}
        return {d: base.get(d, 0.0) for d in dims}
