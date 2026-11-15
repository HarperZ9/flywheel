"""distribution-invariant-v1 -- the tier-2 oracle over Distribution.

Re-derives normalization + moments from the raw mass and checks claims against the
re-derivation. SOUNDNESS: VERIFIED only when the recomputation matches; an empty,
non-finite, or zero-mass distribution, or an absent claim, is UNVERIFIABLE."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .certificate import Certificate, Verdict
from .composition import meet_verdicts
from .distribution import Distribution

_ORACLE = "distribution-invariant-v1"


@dataclass(frozen=True)
class DistributionClaim:
    claim: str
    dist: Distribution
    mean: float | None = None
    variance: float | None = None
    rel_tol: float = 1e-9


def check_normalized(d: Distribution, *, tol: float = 1e-9) -> Certificate:
    claim = "normalized pmf (sum=1, 0<=p<=1)"
    probs = [p for _, p in d.pairs]
    if not probs or not all(math.isfinite(p) for p in probs):
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", "empty or non-finite mass"),))
    if not math.isfinite(tol) or tol < 0.0:   # an inf/nan/neg tol would launder a false VERIFIED
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", f"invalid tol: {tol!r}"),))
    for p in probs:
        if p < 0.0 or p > 1.0:
            return Certificate(claim, Verdict.REFUTED, _ORACLE, (("bad_prob", repr(p)),))
    s = math.fsum(probs)
    verdict = Verdict.VERIFIED if abs(s - 1.0) <= tol else Verdict.REFUTED
    return Certificate(claim, verdict, _ORACLE, (("total", repr(s)), ("tol", repr(tol))))


def check_moments(d: Distribution, *, mean=None, variance=None,
                  rel_tol: float = 1e-9) -> Certificate:
    claim = f"moments(mean={mean}, variance={variance})"
    if mean is None and variance is None:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", "no moment claimed"),))
    if not math.isfinite(rel_tol) or rel_tol < 0.0:   # an inf/nan/neg tol would launder a false VERIFIED
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", f"invalid rel_tol: {rel_tol!r}"),))
    t = d.total()
    if not math.isfinite(t) or t <= 0.0:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", "zero or non-finite mass"),))
    if not all(math.isfinite(x) and math.isfinite(p) for x, p in d.pairs):
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", "non-finite outcome or probability"),))
    derived = {"mean": d.mean(), "variance": d.variance()}
    evidence: list[tuple[str, str]] = []
    for label, claimed in (("mean", mean), ("variance", variance)):
        if claimed is None:
            continue
        # abs_tol=rel_tol so a true zero mean/variance claim verifies (pure rel_tol
        # rejects anything compared against 0); sound -- inf/nan/neg rel_tol rejected above.
        if not math.isclose(claimed, derived[label], rel_tol=rel_tol, abs_tol=rel_tol):
            return Certificate(claim, Verdict.REFUTED, _ORACLE,
                               ((f"claimed_{label}", repr(claimed)),
                                (f"derived_{label}", repr(derived[label]))))
        evidence.append((label, repr(derived[label])))
    return Certificate(claim, Verdict.VERIFIED, _ORACLE, tuple(evidence))


def check_distribution(d: Distribution, *, mean=None, variance=None,
                       rel_tol: float = 1e-9, tol: float = 1e-9) -> Certificate:
    """Normalization AND (if a moment is claimed) moment-correctness, combined
    fail-closed: REFUTED dominates; any UNVERIFIABLE => UNVERIFIABLE; else VERIFIED."""
    parts = [("normalized", check_normalized(d, tol=tol))]
    if mean is not None or variance is not None:
        parts.append(("moments", check_moments(d, mean=mean, variance=variance, rel_tol=rel_tol)))
    verdict = meet_verdicts(c.verdict for _, c in parts)   # proven lattice meet (no hand-rolled 3-valued logic)
    claim = " & ".join(name for name, _ in parts)
    evidence = tuple((f"{name}:{k}", v) for name, c in parts for k, v in c.evidence)
    return Certificate(claim, verdict, _ORACLE, evidence)
