"""valve_flywheel.py — the natural valve flywheel: a ratchet on verified progress.

A flywheel STORES; a valve makes the store ONE-WAY and THRESHOLD-GATED. Joined, they
are a ratchet: a check valve admits only forward pressure above a cracking threshold
and blocks backflow, while the flywheel accumulates what passes and holds it. The
natural version of the amortization loop — intermittent, bidirectional input becomes
steady, monotone, non-regressing output.

The harness reading, which is why this is a mechanism and not a picture: banked
verified capability (the receipt cache, the verified corpus) only GROWS. A worse
proposal cannot lower it (the check valve blocks backflow = no regression), and it is
stored so it is not re-earned (the flywheel). The valve's THRESHOLD is the accept
criterion; the valve's ONE-WAY-NESS is the no-regression guarantee.

The load-bearing tie to everything else this session: the no-backflow guarantee holds
IFF the threshold is EXTERNALIZED. A self-authored valve — one whose threshold the flow
itself can set — is a valve you can push open in reverse: it admits regression as
"progress" and the ratchet breaks (stored can decrease). Only a non-self-authored
threshold makes a true check valve. Same externalization asymmetry, now on the
temporal/directional axis (no regression over time).

HONEST bounds: this is an idealized check-valve + accumulator, not a physical valve —
no hysteresis, leakage, cracking dynamics, or water-hammer. "No backflow" is a design
invariant contingent on the externalized threshold, not a physical law.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValveFlywheel:
    """A check-valve + flywheel accumulator. `threshold` is the cracking pressure:
    forward pressure at or above it is admitted and accumulates; backflow (pressure
    <= 0) and sub-threshold pressure are blocked. `stored` is monotone non-decreasing.
    If `self_authored` is True the valve lets the flow lower the threshold to admit
    whatever arrives — including backflow — which breaks the ratchet."""
    threshold: float
    self_authored: bool = False
    stored: float = 0.0
    admitted: int = 0
    blocked_backflow: int = 0
    blocked_subthreshold: int = 0
    history: list = field(default_factory=list)

    def pump(self, pressure: float) -> bool:
        thr = self.threshold
        if self.self_authored:
            # the flow sets the gate to admit itself — a valve pushed open from either side
            thr = min(self.threshold, pressure)
        if not self.self_authored and pressure <= 0:      # check valve: block backflow
            self.blocked_backflow += 1
            self.history.append(self.stored)
            return False
        if pressure < thr:                                 # below cracking pressure
            self.blocked_subthreshold += 1
            self.history.append(self.stored)
            return False
        self.stored += pressure                            # flywheel accumulates
        self.admitted += 1
        self.history.append(self.stored)
        return True

    def is_monotone(self) -> bool:
        return all(b >= a for a, b in zip(self.history, self.history[1:]))


def run_stream(threshold: float, pressures: list, *, self_authored: bool = False) -> dict:
    """Pump a stream of pressures (positive = improvement, negative = regression) and
    report the ratchet's behavior."""
    v = ValveFlywheel(threshold=threshold, self_authored=self_authored)
    for p in pressures:
        v.pump(p)
    return {"threshold": threshold, "self_authored": self_authored,
            "stored": round(v.stored, 3), "admitted": v.admitted,
            "blocked_backflow": v.blocked_backflow,
            "blocked_subthreshold": v.blocked_subthreshold,
            "monotone_no_regression": v.is_monotone(),
            "final_curve": [round(x, 2) for x in v.history]}


def externalization_contrast(pressures: list, threshold: float = 1.0) -> dict:
    """The tie to the rest: the SAME stream through an externalized valve (fixed
    threshold, true check valve) vs a self-authored valve (flow sets the gate). The
    externalized one ratchets (monotone, no regression); the self-authored one admits
    backflow and breaks the ratchet."""
    ext = run_stream(threshold, pressures, self_authored=False)
    self_ = run_stream(threshold, pressures, self_authored=True)
    return {"externalized": ext, "self_authored": self_,
            "ratchet_holds_only_when_externalized":
                ext["monotone_no_regression"] and not self_["monotone_no_regression"]}
