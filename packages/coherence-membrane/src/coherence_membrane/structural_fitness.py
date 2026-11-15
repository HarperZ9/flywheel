"""structural_fitness -- a reconcile criterion for grounded aesthetic/structural quality.

Beauty made SOUND: not a learned "looks-good" score (the ungrounded-critic trap, the
Cell *Patterns* mode-collapse failure), but conformance to a chosen MATHEMATICAL
INVARIANT -- measured, thresholded, and carried as a re-checkable proof. The criterion
is thin and generic; all the TASTE lives in the injected `deviation` measure (which
ideal, and how far the form is from it). VERIFIED-fit iff the measured deviation is
within tolerance, REFUTED beyond, UNVERIFIABLE when the measure cannot decide (it
raised, or returned a non-finite value -- "can't measure" is not "unfit"). This is the
SECOND HALF of grounded creativity: compose it with novelty (the proven lattice meet)
and a work is good iff it is NOVEL and STRUCTURED -- the target between derivative
mode-collapse and noise."""
from __future__ import annotations

import math

from .certificate import Certificate, Verdict
from .reconcile import Criterion

_ORACLE = "structural-fitness-v1"


def structural_fitness_criterion(deviation, *, tolerance) -> Criterion:
    """A Criterion judging a perceived form FIT iff `deviation(form) <= tolerance`.
    `deviation(form) -> float` is a caller-supplied measure of distance from a chosen
    mathematical ideal (>= 0; 0 = the ideal exactly); `tolerance` is the accepted slack.
    VERIFIED-fit / REFUTED-unfit / UNVERIFIABLE (the measure raised, or returned a
    non-real / NaN / infinite deviation -- inability to measure is not unfitness).
    `tolerance` must be a real, FINITE, non-negative number: a non-finite tolerance
    (e.g. inf would verify everything) is a construction-time programmer error, raised
    loudly HERE; `judge` itself never raises on a valid criterion."""
    if not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance):
        raise ValueError(f"tolerance must be a real, finite number, got {tolerance!r}")
    if tolerance < 0:
        raise ValueError(f"tolerance must be >= 0, got {tolerance!r}")

    def judge(form) -> Certificate:
        try:
            d = deviation(form)
        except Exception as exc:
            return Certificate("structural fitness", Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", repr(exc)),))
        if not isinstance(d, (int, float)) or not math.isfinite(d):
            return Certificate("structural fitness", Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", f"measure returned non-finite deviation {d!r}"),))
        verdict = Verdict.VERIFIED if d <= tolerance else Verdict.REFUTED
        claim = f"structurally fit: deviation {d!r} <= tolerance {tolerance!r}"
        return Certificate(claim, verdict, _ORACLE,
                           (("deviation", repr(d)), ("tolerance", repr(tolerance))))

    return Criterion("structural-fitness", judge)
