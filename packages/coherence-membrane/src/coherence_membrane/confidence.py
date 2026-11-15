"""confidence -- a DERIVED degree-of-confidence valuation beside the verdict lattice.

The verifier ladder propagates a graded confidence ("high / moderate / low"). Those
words are ad-hoc; this module gives them a DERIVED foundation instead of asserting a
scale. Cox's theorem (1946) and its modern, weaker-hypothesis restatement by Knuth &
Skilling (*Foundations of Inference*, 2012; "Probability Theory is an Extension of
Logic") show: ANY real-valued degree of plausibility on a lattice of propositions
that is (i) ordered consistently and (ii) combined ASSOCIATIVELY must -- after a
monotone re-scaling -- obey the SUM and PRODUCT rules, i.e. it IS (a representation of)
probability. The associativity is the load-bearing axiom: a consistent valuation has
no freedom to be anything but probability once you demand that combining A-then-(B,C)
agrees with combining (A,B)-then-C.

So the confidence carried with a DECIDED verdict is not invented here; the only
associative, order-respecting, [0,1]-valued combine for a CONJUNCTION of independent
graded steps is the PRODUCT (the product rule, independent case):

    combine(p, q) = p * q          (associative, commutative,
                                    identity 1 = certain, absorbing 0 = impossible)

That is exactly the right algebra BESIDE the verdict meet: composing two graded
`VERIFIED` steps multiplies their confidences (a long argument is no more confident
than its product), and `combine` is associative *for the same reason the meet is* --
so the two layers move together. The qualitative three-valued lattice
(`VERIFIED`/`REFUTED`/`UNVERIFIABLE`) stays PRIMARY; this quantitative degree is the
Knuth-Skilling completion ONLY where a witness actually supports grading.

Soundness invariants (this layer can NEVER manufacture trust):
  * Confidence attaches ONLY to a DECIDED verdict (`VERIFIED` / `REFUTED`) produced by
    a graded oracle. An `UNVERIFIABLE` verdict carries confidence ``None`` -- a NON-
    probability ("no witness"), explicitly NOT ``0.5``. (p=0.5 would be a *claim* of
    maximal uncertainty; "no witness" is the absence of any claim -- a different thing.)
  * A confidence value -- however high -- NEVER promotes a non-decided verdict to
    `VERIFIED`, and never changes ANY verdict. The lattice verdict is primary; this is
    a secondary, optional annotation. `decide_*` here returns the verdict UNCHANGED.
  * Additive + optional: existing `Certificate` call sites are untouched. Confidence
    rides ALONGSIDE a certificate (a thin `Graded` wrapper, or an evidence key via
    `annotate`), never inside the frozen `Certificate`'s verdict semantics.

Attribution (study + cite, never strip): 3cycle, "Probability Theory is an Extension
of Logic" (id ``0yF9TvMeAzM``); Knuth & Skilling, *Foundations of Inference* (2012);
R. T. Cox, "Probability, Frequency and Reasonable Expectation" (1946); E. T. Jaynes,
*Probability Theory: The Logic of Science*. Stdlib only; zero external dependency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable

from .certificate import Certificate, Verdict

# The identity of the associative combine: certain confidence. Composing with CERTAIN
# leaves a confidence unchanged (it is the unit of the product rule). The absorbing
# element is 0.0 (an impossible step makes any conjunction impossible).
CERTAIN: float = 1.0


def _is_real_unit(x) -> bool:
    """True iff x is a real number in the closed unit interval [0, 1] (NaN rejected).

    Accepts any `numbers.Real` (int / float / `fractions.Fraction` / `decimal`-free
    rationals) so an EXACT degree can be supplied; rejects `bool` (a degree is not a
    flag) and anything non-real. Non-finite (inf/NaN) is out of [0,1] and rejected."""
    return (
        isinstance(x, Real)
        and not isinstance(x, bool)
        and math.isfinite(float(x))
        and 0.0 <= float(x) <= 1.0
    )


def confidence_of(value) -> float:
    """Validate a degree of confidence: a real number in [0, 1]. Raised loudly at the
    boundary (a degree outside [0,1] is not a probability and cannot be re-scaled to
    one). This is the construction guard, mirroring novelty/structural_fitness: the
    producer's grade is checked HERE so the combine never has to defend against junk."""
    if not _is_real_unit(value):
        raise ValueError(f"confidence must be a real number in [0, 1], got {value!r}")
    return float(value)


def combine(p: float, q: float) -> float:
    """The Knuth-Skilling / Cox conjunction combine: the PRODUCT rule (independent
    case). Associative, commutative; identity ``CERTAIN`` (1.0), absorbing 0.0. This is
    the UNIQUE associative, order-respecting [0,1] combine for conjoining independent
    graded steps -- composing two graded `VERIFIED` steps multiplies their confidence.

    Inputs are validated to [0,1]; the result is clamped into [0,1] purely to absorb
    floating-point drift (e.g. 0.9999999999999999), never to launder an out-of-range
    input -- those raise. Pure + deterministic."""
    a = confidence_of(p)
    b = confidence_of(q)
    return min(1.0, max(0.0, a * b))


def combine_all(values: Iterable[float]) -> float:
    """Fold ``combine`` over many confidences. The EMPTY fold is ``CERTAIN`` (the
    identity), exactly as the lattice meet's empty fold is its top -- a conjunction of
    NO graded steps asserts nothing extra, so it does not lower confidence. (As with
    `compose`, a caller that must fail closed on *no evidence* guards emptiness at the
    VERDICT layer -- empty `compose` is already `UNVERIFIABLE`, which carries None here,
    so an empty graded composition is never silently 'certain'.)"""
    acc = CERTAIN
    for v in values:
        acc = combine(acc, v)
    return acc


@dataclass(frozen=True)
class Graded:
    """A `Certificate` with an OPTIONAL derived confidence riding beside it.

    `certificate` -- the primary, unchanged verdict object (the lattice verdict is
                     authoritative).
    `confidence`  -- a degree in [0, 1] for a DECIDED verdict from a graded oracle, or
                     ``None`` for `UNVERIFIABLE` (no witness -> NOT 0.5) and for any
                     un-graded decided verdict (a grade was simply not supplied).

    The class enforces the soundness invariant at construction: a non-decided verdict
    can carry NO confidence (`UNVERIFIABLE` + a number is a contradiction -- a witness-
    free verdict has nothing to be confident about). The verdict is NEVER read from or
    written by the confidence; this wrapper cannot promote anything."""

    certificate: Certificate
    confidence: float | None = None

    def __post_init__(self) -> None:
        decided = self.certificate.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        if self.confidence is None:
            return
        if not decided:
            # fail-closed: a non-decided (UNVERIFIABLE) verdict must not carry a degree.
            raise ValueError(
                "confidence attaches only to a DECIDED verdict (VERIFIED/REFUTED); "
                f"{self.certificate.verdict.value} carries no confidence (not 0.5)"
            )
        object.__setattr__(self, "confidence", confidence_of(self.confidence))

    @property
    def verdict(self) -> Verdict:
        """The PRIMARY verdict, passed straight through -- confidence never alters it."""
        return self.certificate.verdict

    @property
    def is_decided(self) -> bool:
        return self.certificate.verdict in (Verdict.VERIFIED, Verdict.REFUTED)

    def to_dict(self) -> dict:
        d = self.certificate.to_dict()
        d["confidence"] = self.confidence  # None for UNVERIFIABLE / un-graded
        return d


def grade(certificate: Certificate, confidence: float | None) -> Graded:
    """Attach a derived confidence to a certificate (the optional annotation entry).

    A DECIDED verdict may carry a [0,1] confidence; an `UNVERIFIABLE` verdict is FORCED
    to ``None`` (no witness -> no probability, explicitly not 0.5) regardless of what is
    passed -- the soundness rule, applied at the door rather than trusted of the caller.
    Never changes the verdict."""
    if certificate.verdict not in (Verdict.VERIFIED, Verdict.REFUTED):
        return Graded(certificate, None)
    return Graded(certificate, confidence)


def annotate(certificate: Certificate, confidence: float | None) -> Certificate:
    """Additive, in-band variant: return a NEW `Certificate` whose evidence carries the
    confidence as a labelled key, leaving claim/verdict/oracle byte-identical. Use this
    when a wrapper is unwanted and the degree should travel inside the existing evidence
    channel. An `UNVERIFIABLE` verdict is annotated ``confidence=none`` (never a number).
    The verdict is unchanged; only an evidence pair is appended."""
    if certificate.verdict in (Verdict.VERIFIED, Verdict.REFUTED) and confidence is not None:
        value = repr(confidence_of(confidence))
    else:
        value = "none"
    return Certificate(
        certificate.claim,
        certificate.verdict,
        certificate.oracle,
        certificate.evidence + (("confidence", value),),
    )


def compose_confident(graded: Iterable[Graded]) -> float | None:
    """Combine the confidences of a multi-step graded argument via the product rule --
    the confidence ANNOTATION that rides beside `composition.compose`'s verdict.

    Returns ``None`` (no aggregate confidence) the moment soundness forbids a number:
      * any step is UNVERIFIABLE (carries None) -> the conjunction has no witness-backed
        degree -> None (mirrors the verdict meet attenuating to UNVERIFIABLE);
      * any DECIDED step lacks a confidence (None) -> the product is undefined -> None;
      * an empty argument -> None (nothing graded; the verdict layer already fails
        closed to UNVERIFIABLE on empty).
    Only when EVERY step is decided AND graded does it return their product. This NEVER
    yields or implies a verdict; it is a secondary number beside the primary meet."""
    steps = list(graded)
    if not steps:
        return None
    confidences: list[float] = []
    for g in steps:
        if not g.is_decided or g.confidence is None:
            return None
        confidences.append(g.confidence)
    return combine_all(confidences)
