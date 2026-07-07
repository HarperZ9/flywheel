"""backflow.py — the three real backflow mechanisms, on the frontier valve.

valve_flywheel modeled backflow crudely as `pressure <= 0` (a SIGN check). Real
backflow is a PRESSURE DIFFERENTIAL, and that crude model misses the most important
case. This refines it with the three actual mechanisms, on a FRONTIER (level) valve:
there is a current head H (the banked verified capability level), and a candidate at
level L opens the check valve only if it EXCEEDS the head (upstream > downstream).

  1. BACKPRESSURE — 0 < L <= H. A POSITIVE candidate that is still <= the current
     head. Downstream pressure meets/exceeds upstream, so the frontier does NOT
     advance. This is the case the sign-only valve wrongly ADMITTED: a positive
     regression. The frontier valve blocks it.
  2. BACKSIPHONAGE — an external withdrawal/vacuum (demand < 0) that would DRAIN the
     banked head. The ratchet forbids draining verified state; blocked.
  3. BOUNDARY-LAYER SEPARATION — a sustained ADVERSE GRADIENT (a run of candidates
     each just below the head). A frontier valve anchored to the EXTERNALIZED head
     stays attached (head holds, no reversal). A self-authored valve that lets its
     reference RELAX under sustained adverse pressure SEPARATES: the reference drifts
     down and recirculation (regression) sets in. Same externalization asymmetry.

HONEST bounds: still not CFD — no real pressure field, momentum, viscosity, or
Navier-Stokes. "Separation" here is a discrete relaxation analogy, not a boundary
layer. The value is a correctly-typed no-regression valve (catches positive
regressions the sign model missed) plus the named-mechanism taxonomy, testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FrontierValve:
    """Level (frontier) check valve. `head` is the current banked capability level;
    the valve opens only for a candidate that exceeds it. `relax_under_adverse`
    models a SELF-AUTHORED valve whose reference drifts down under sustained adverse
    pressure (boundary-layer separation)."""
    head: float = 0.0
    relax_under_adverse: bool = False
    admitted: int = 0
    backpressure_blocked: int = 0
    backsiphonage_blocked: int = 0
    adverse_run: int = 0
    separated: bool = False
    history: list = field(default_factory=list)

    def apply(self, level: float, *, demand: float = 0.0) -> str:
        # backsiphonage: an external vacuum trying to draw the banked head back out
        if demand < 0:
            if self.relax_under_adverse:
                self.head += demand            # self-authored valve lets it drain
                self.separated = True
                self.history.append(self.head)
                return "SIPHONED"
            self.backsiphonage_blocked += 1
            self.history.append(self.head)
            return "BLOCKED_BACKSIPHONAGE"
        if level > self.head:                   # check valve opens: upstream > downstream
            self.head = level
            self.admitted += 1
            self.adverse_run = 0
            self.history.append(self.head)
            return "ADMITTED"
        # 0 <= level <= head: adverse (downstream >= upstream) -> backpressure
        self.backpressure_blocked += 1
        self.adverse_run += 1
        if self.relax_under_adverse:
            # sustained adverse gradient relaxes the reference -> separation
            self.head = level                  # reference drifts down to the adverse input
            self.separated = True
        self.history.append(self.head)
        return "BLOCKED_BACKPRESSURE"

    def is_monotone(self) -> bool:
        return all(b >= a for a, b in zip(self.history, self.history[1:]))


def run_levels(levels: list, *, relax_under_adverse: bool = False,
               demands: list | None = None) -> dict:
    """Feed a stream of candidate LEVELS (and optional demands) through the frontier
    valve. `levels` are absolute quality levels, not deltas."""
    v = FrontierValve(relax_under_adverse=relax_under_adverse)
    demands = demands or [0.0] * len(levels)
    verdicts = [v.apply(l, demand=d) for l, d in zip(levels, demands)]
    return {"final_head": round(v.head, 3), "admitted": v.admitted,
            "backpressure_blocked": v.backpressure_blocked,
            "backsiphonage_blocked": v.backsiphonage_blocked,
            "separated": v.separated, "monotone": v.is_monotone(),
            "verdicts": verdicts, "head_curve": [round(x, 2) for x in v.history]}


def sign_model_would_admit(levels: list, head0: float = 0.0) -> list:
    """What the OLD sign-only valve (block iff pressure<=0) would have admitted:
    every positive level. The positive regressions it wrongly lets through are the
    ones the frontier valve catches as backpressure."""
    return [l for l in levels if l > 0]


def externalization_contrast(levels: list) -> dict:
    """The tie: the same adverse stream through an externalized frontier valve (head
    holds, no separation) vs a self-authored one (reference relaxes, separates)."""
    ext = run_levels(levels, relax_under_adverse=False)
    self_ = run_levels(levels, relax_under_adverse=True)
    return {"externalized": ext, "self_authored": self_,
            "only_selfauthored_separates": (not ext["separated"]) and self_["separated"],
            "only_externalized_monotone": ext["monotone"] and not self_["monotone"]}
