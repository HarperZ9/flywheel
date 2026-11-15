"""refine -- the reconcile, deepened into a self-improving, refine-until-correct primitive.

The reconcile judges an artifact once (perceive -> criterion -> certificate). refine
GENERALIZES it: judge against GRADED criteria (each yielding a margin, labelled objective or
subjective), measure their COHESION (the harmonic mean of margins -- high only when every axis
is healthy AND balanced), and if the candidate is not CORRECT (all margins past a positive
target AND cohesive AND any hard guard holds), REFLECT on the weakest axis and re-iterate --
until correct, or until an honest budget is spent (then it says which axis fell short, never a
false "correct"). A binary action (one grader, max_iter=1, target<=0, bar<=0, no guard)
degenerates to exactly the reconcile. The whole reflect->grade trajectory is carried as a
re-checkable witness. Fail-closed throughout: a deviation, generate, or adjust that raises (or
a non-numeric deviation) degrades to an honest outcome, never a crash and never a false
"correct". Stdlib only; depends only on the Grade/cohesion contracts, never on a specific oracle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class GradedCriterion:
    """A named, kind-labelled judge that yields a MARGIN, not a verdict.
    deviation(form) -> float >= 0 (0 = the ideal); tolerance > 0 is the failing threshold."""
    name: str
    kind: str            # "objective" | "subjective"
    deviation: Callable[[Any], float]
    tolerance: float

    def __post_init__(self) -> None:
        if self.kind not in ("objective", "subjective"):
            raise ValueError(f"kind must be objective|subjective, got {self.kind!r}")
        if (not isinstance(self.tolerance, (int, float)) or isinstance(self.tolerance, bool)
                or not math.isfinite(self.tolerance) or self.tolerance <= 0):
            raise ValueError(f"tolerance must be a finite positive number, got {self.tolerance!r}")


@dataclass(frozen=True)
class Grade:
    name: str
    kind: str
    deviation: float
    tolerance: float
    margin: float
    ok: bool


def grade(criterion: GradedCriterion, form) -> Grade:
    """Measure one criterion. A deviation that raises, is non-numeric (incl. bool), non-finite,
    or negative -> margin -inf, ok False (fail-closed: 'cannot trust the measure' is never
    'within tolerance'; a buggy grader returning a falsy value must NOT read as perfect)."""
    try:
        raw = criterion.deviation(form)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"deviation must be a real number, got {type(raw).__name__}")
        d = float(raw)
    except Exception:
        d = float("inf")
    if not math.isfinite(d) or d < 0:
        margin = float("-inf")
    else:
        margin = (criterion.tolerance - d) / criterion.tolerance
    return Grade(criterion.name, criterion.kind, d, criterion.tolerance, margin, margin >= 0.0)


def cohesion(margins) -> float:
    """The coordination measure: 0.0 if there are no margins or ANY margin <= 0 / non-finite
    (a failing or unmeasurable axis); else the HARMONIC MEAN of the margins. High only when
    every axis is healthy AND balanced -- one weak axis tanks it (so a lopsided candidate that
    bare-passes each axis is still not cohesive). Bounded in (0, 1] when defined (margins <= 1)."""
    ms = list(margins)
    if not ms or any((not math.isfinite(m)) or m <= 0.0 for m in ms):
        return 0.0
    return len(ms) / sum(1.0 / m for m in ms)


@dataclass(frozen=True)
class Reflection:
    weakest: str
    kind: str
    margin: float
    shortfall: float          # target_margin - weakest.margin (how far from comfortable)
    margins: tuple            # ((name, margin), ...)
    guard_ok: bool


def reflect(grades, target_margin: float, guard_ok: bool = True) -> Reflection:
    """Grounded self-critique: name the weakest axis and its shortfall from the comfort target."""
    worst = min(grades, key=lambda g: g.margin)
    return Reflection(worst.name, worst.kind, worst.margin, target_margin - worst.margin,
                      tuple((g.name, g.margin) for g in grades), guard_ok)


def is_correct(grades, coh: float, guard_ok: bool, *, target_margin: float, cohesion_bar: float) -> bool:
    """CORRECT, not good-enough: every axis comfortably inside (>= target_margin > 0 in real use),
    the axes cohesive (cohesion >= bar), AND the hard guard holds. Every clause is necessary."""
    return (guard_ok
            and all(g.margin >= target_margin for g in grades)
            and coh >= cohesion_bar)


@dataclass(frozen=True)
class RefineStep:
    iteration: int
    grades: tuple
    cohesion: float
    correct: bool
    guard_ok: bool
    reflection: Reflection


@dataclass(frozen=True)
class RefineOutcome:
    candidate: Any
    status: str               # "correct" | "short"
    trajectory: tuple
    short_axis: str | None    # the weakest axis, or a "<callback>-failed: ..." reason, when "short"


def refine(generate, graders, adjust, *, guard=None, target_margin: float, cohesion_bar: float,
           max_iter: int, perceive=lambda c: c) -> RefineOutcome:
    """Refine until CORRECT, or until an honest budget is spent.

    generate(state) -> candidate; perceive(candidate) -> form; each grader is graded; cohesion +
    correctness computed; reflect on the weakest axis; adjust(reflection, state) steers the next
    iteration. NEVER returns "correct" unless is_correct holds. On budget exhaustion returns the
    best guard-passing candidate (highest cohesion) with status "short" + the weakest axis. A
    generate/adjust callback that RAISES degrades to an honest "short" (never a crash).
    """
    if not graders:
        raise ValueError("refine requires at least one grader")
    if max_iter is None or max_iter < 1:
        raise ValueError("refine requires max_iter >= 1")
    # A negative target_margin or cohesion_bar would let a FAILING axis (margin < 0) read as
    # "correct" -> validate them, closing that false-correct escape. >= 0 (not > 0) keeps the
    # documented degenerate=reconcile mode (target=0, bar=0).
    for _label, _val in (("target_margin", target_margin), ("cohesion_bar", cohesion_bar)):
        if (not isinstance(_val, (int, float)) or isinstance(_val, bool)
                or not math.isfinite(_val) or _val < 0):
            raise ValueError(f"refine requires {_label} >= 0 (finite), got {_val!r}")
    state = None
    trajectory: list = []
    best = None            # (RefineStep, candidate) with the highest cohesion among guard-passing
    last_candidate = None
    last_refl = None
    for i in range(max_iter):
        try:
            candidate = generate(state)
        except Exception as exc:                          # fail-closed: a broken generator -> honest short
            return RefineOutcome(best[1] if best is not None else last_candidate, "short",
                                 tuple(trajectory), f"generate-failed: {exc!r}")
        last_candidate = candidate
        form = perceive(candidate)
        grades = tuple(grade(g, form) for g in graders)
        coh = cohesion([g.margin for g in grades])
        gok = True if guard is None else bool(guard(candidate))
        correct = is_correct(grades, coh, gok, target_margin=target_margin, cohesion_bar=cohesion_bar)
        refl = reflect(grades, target_margin, gok)
        last_refl = refl
        step = RefineStep(i, grades, coh, correct, gok, refl)
        trajectory.append(step)
        if gok and (best is None or coh > best[0].cohesion):
            best = (step, candidate)
        if correct:
            return RefineOutcome(candidate, "correct", tuple(trajectory), None)
        try:
            state = adjust(refl, state)
        except Exception as exc:                          # fail-closed: a broken steer -> honest short
            return RefineOutcome(best[1] if best is not None else candidate, "short",
                                 tuple(trajectory), f"adjust-failed: {exc!r}")
    out_candidate = best[1] if best is not None else last_candidate
    short_axis = (best[0].reflection.weakest if best is not None
                  else (last_refl.weakest if last_refl is not None else None))
    return RefineOutcome(out_candidate, "short", tuple(trajectory), short_axis)
