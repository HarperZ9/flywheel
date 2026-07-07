"""turbulence.py — where re-checkability breaks, and what survives it.

Turbulence's sharpest property for this project is not eddies, it is
IRREPRODUCIBILITY: a deterministic system whose exact trajectory cannot be re-run to
the same detail (sensitive dependence on initial conditions). That is a direct
challenge to the harness, which rests on re-checkability — emit a receipt anyone can
re-execute to the same verdict (MATCH).

The honest resolution, made precise on a deterministic chaotic map (the logistic map,
a dynamical-systems analog of the laminar->turbulent transition, tuned by r as a
Reynolds-like control):

  - LAMINAR (low r): the trajectory is reproducible. A trajectory-level receipt
    re-checks (MATCH). The reconcile works directly on the path.
  - TURBULENT (high r, positive Lyapunov exponent): the exact trajectory does NOT
    re-check — a tiny perturbation (a reordered float op, different hardware) diverges
    exponentially, so a trajectory receipt DRIFTs even though the system is fully
    deterministic. BUT the STATISTICAL INVARIANT (the invariant measure / histogram)
    IS reproducible across seeds and re-checks (MATCH). What you conserve is the
    criterion, never the bits.

The load-bearing lesson: above the critical parameter, a verifier that demands
TRAJECTORY match reports a spurious DRIFT (false alarm) — it is checking the wrong
invariant. The fix is to witness the DISTRIBUTION. The harness already embodies this:
its oracle checks a semantic invariant (does the candidate PASS the tests) not the
exact tokens, which is why LLM sampling non-determinism ("turbulent" output) does not
break it. This module makes the boundary explicit and measurable.

HONEST bounds: a 1D logistic map is NOT turbulence. Turbulence is spatiotemporal chaos
in Navier-Stokes with an energy cascade, vorticity, and the Kolmogorov -5/3 spectrum,
none of which are here. This is the DYNAMICAL-SYSTEMS core (sensitive dependence +
statistical reproducibility). The lesson about re-checkability transports; the physics
does not.
"""
from __future__ import annotations

import math


def trajectory(r: float, x0: float, n: int, burn: int = 0) -> list[float]:
    x = x0
    out = []
    for i in range(n + burn):
        x = r * x * (1.0 - x)
        if i >= burn:
            out.append(x)
    return out


def lyapunov(r: float, x0: float = 0.3, n: int = 4000, burn: int = 200) -> float:
    """Mean log|dx'/dx| along the orbit. > 0 => chaos (trajectory not re-checkable);
    < 0 => stable/periodic (laminar, re-checkable)."""
    x = x0
    for _ in range(burn):
        x = r * x * (1.0 - x)
    s = 0.0
    for _ in range(n):
        d = abs(r * (1.0 - 2.0 * x))
        s += math.log(d) if d > 0 else -30.0
        x = r * x * (1.0 - x)
    return s / n


def trajectory_rechecks(r: float, x0: float, n: int = 200, eps: float = 1e-9,
                        tol: float = 1e-3, tail: int = 30) -> bool:
    """Re-run the orbit from a MINUTELY perturbed start (a reordered-float-op re-run).
    True iff the tail still matches within tol — i.e. the trajectory receipt reproduces.
    Fails under sensitive dependence (chaos)."""
    a = trajectory(r, x0, n)
    b = trajectory(r, x0 + eps, n)
    return max(abs(u - v) for u, v in zip(a[-tail:], b[-tail:])) < tol


def _hist(traj: list[float], bins: int = 10) -> list[float]:
    counts = [0] * bins
    for x in traj:
        k = min(bins - 1, int(x * bins))
        counts[k] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


def invariant_rechecks(r: float, x0a: float = 0.11, x0b: float = 0.71,
                       n: int = 8000, bins: int = 10, tol: float = 0.05) -> bool:
    """The STATISTICAL invariant from two DIFFERENT seeds. True iff the two histograms
    match within tol (L1/2) after burn-in — the invariant measure reproduces even when
    the trajectory does not."""
    ha = _hist(trajectory(r, x0a, n, burn=300), bins)
    hb = _hist(trajectory(r, x0b, n, burn=300), bins)
    l1 = sum(abs(a - b) for a, b in zip(ha, hb))
    return (l1 / 2.0) < tol


def regime(r: float) -> dict:
    """Classify r and report which receipt survives: trajectory vs invariant."""
    lam = lyapunov(r)
    return {"r": r, "lyapunov": round(lam, 4),
            "regime": "turbulent" if lam > 0 else "laminar",
            "trajectory_rechecks": trajectory_rechecks(r, 0.3),
            "invariant_rechecks": invariant_rechecks(r)}


def false_drift_from_wrong_invariant(r: float) -> dict:
    """The lesson: in the turbulent regime, demanding TRAJECTORY match yields a spurious
    DRIFT while the correct (distribution) witness yields MATCH. Checking the wrong
    invariant manufactures a false alarm on a deterministic system."""
    traj_ok = trajectory_rechecks(r, 0.3)
    inv_ok = invariant_rechecks(r)
    return {"r": r,
            "trajectory_witness": "MATCH" if traj_ok else "DRIFT",
            "distribution_witness": "MATCH" if inv_ok else "DRIFT",
            "false_drift": (not traj_ok) and inv_ok}   # wrong-invariant false alarm
