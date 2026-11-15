#!/usr/bin/env python3
"""Control-certificate demo: a double integrator whose residuals are COMPUTED.

Every number in this demo is measured by running the closed loop, never
hand-entered. The Lyapunov certificate itself is SYNTHESIZED here by solving
the discrete Lyapunov equation (P = Q + A^T P A by fixed-point iteration), so
the packet's provenance field honestly says "synthesized". The stabilizing
gain yields a MATCH; flipping the gain destabilizes the SAME plant and the
SAME certificate fails it (DRIFT). That second run is the point: a verifier
that cannot fail on a known-bad input is not a verifier.

An earlier draft of this demo asserted the identity-weighted candidate
V = x1^2 + x2^2 and the check FAILED it on the stable loop (measured increase
1.3): correct behavior, wrong certificate. The fix was a real certificate,
not a looser check.

Plant (discrete double integrator, dt = 0.05, u = -(k1*x1 + k2*x2)):
    A_cl = [[1, dt], [-dt*k1, 1 - dt*k2]]

Run from a checkout without installing:

    PYTHONPATH=src python examples/control_certificate/demo.py
"""

from __future__ import annotations

import hashlib
import json
import math

from proof_surface.control_certificate import (
    build_control_certificate_packet,
    validate_control_certificate_packet,
)

DT = 0.05
STEPS = 400
STARTS = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.5), (0.7, -0.9)]
STABLE_GAINS = (1.0, 1.6)

Matrix = tuple[tuple[float, float], tuple[float, float]]


def closed_loop(k1: float, k2: float) -> Matrix:
    return ((1.0, DT), (-DT * k1, 1.0 - DT * k2))


def synthesize_lyapunov(a: Matrix, iterations: int = 20000) -> Matrix:
    """Solve P = Q + A^T P A (Q = I) by fixed-point iteration; converges for
    a Schur-stable A. This is the demo's certificate synthesis step."""
    p11, p12, p22 = 1.0, 0.0, 1.0
    for _ in range(iterations):
        (a11, a12), (a21, a22) = a
        # A^T P A for symmetric P = [[p11, p12], [p12, p22]]
        b11 = a11 * (p11 * a11 + p12 * a21) + a21 * (p12 * a11 + p22 * a21)
        b12 = a11 * (p11 * a12 + p12 * a22) + a21 * (p12 * a12 + p22 * a22)
        b22 = a12 * (p11 * a12 + p12 * a22) + a22 * (p12 * a12 + p22 * a22)
        n11, n12, n22 = 1.0 + b11, b12, 1.0 + b22
        if max(abs(n11 - p11), abs(n12 - p12), abs(n22 - p22)) < 1e-15:
            p11, p12, p22 = n11, n12, n22
            break
        p11, p12, p22 = n11, n12, n22
    return ((p11, p12), (p12, p22))


def min_eigenvalue(p: Matrix) -> float:
    (p11, p12), (_, p22) = p
    trace, det = p11 + p22, p11 * p22 - p12 * p12
    return (trace - math.sqrt(max(0.0, trace * trace - 4.0 * det))) / 2.0


def lyapunov(p: Matrix, x: tuple[float, float]) -> float:
    (p11, p12), (_, p22) = p
    return p11 * x[0] * x[0] + 2.0 * p12 * x[0] * x[1] + p22 * x[1] * x[1]


def simulate(k1: float, k2: float) -> list[list[tuple[float, float]]]:
    """One trajectory segment per start; segments are never concatenated for
    the decrease check (a V-jump across two unrelated starts is not a step)."""
    segments: list[list[tuple[float, float]]] = []
    for x1, x2 in STARTS:
        segment: list[tuple[float, float]] = []
        for _ in range(STEPS):
            segment.append((x1, x2))
            u = -(k1 * x1 + k2 * x2)
            x1, x2 = x1 + DT * x2, x2 + DT * u
        segments.append(segment)
    return segments


def max_increase(p: Matrix, segments: list[list[tuple[float, float]]]) -> float:
    """The largest measured V-step along consecutive samples within each
    trajectory; <= 0 means the decrease condition held everywhere."""
    worst = float("-inf")
    for segment in segments:
        for prev, cur in zip(segment, segment[1:]):
            worst = max(worst, lyapunov(p, cur) - lyapunov(p, prev))
    return worst


def log_digest(segments: list[list[tuple[float, float]]]) -> str:
    canon = json.dumps(
        [[[round(a, 12), round(b, 12)] for a, b in seg] for seg in segments]
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def packet_for(p: Matrix, k1: float, k2: float, label: str, bad_residual: float):
    log = simulate(k1, k2)
    samples = sum(len(seg) for seg in log)
    (p11, p12), (_, p22) = p
    return build_control_certificate_packet(
        sources=[{"ref": f"demo:double-integrator:{label}", "sha256": log_digest(log)}],
        system={
            "description": f"double integrator, u = -({k1}*x1 + {k2}*x2)",
            "domain": "robotics",
            "regime": "simulation",
        },
        certificate={
            "kind": "lyapunov",
            "name": "V(x) = x^T P x",
            "declared": f"P = [[{p11:.6f}, {p12:.6f}], [{p12:.6f}, {p22:.6f}]]",
            "provenance": "synthesized",
            "provenance_ref": "discrete Lyapunov iteration P = Q + A^T P A in this demo",
        },
        witnesses=[
            {
                "condition": "positive-definite",
                "residual": max(0.0, -min_eigenvalue(p)),
                "tolerance": 1e-12,
                "method": "closed-form 2x2 minimum eigenvalue of P",
            },
            {
                "condition": "decrease",
                "residual": max(0.0, max_increase(p, log)),
                "tolerance": 1e-9,
                "method": f"max V-step over {samples} simulated samples",
            },
        ],
        negative_fixture={
            "description": "the destabilized-gain run measured in this demo",
            "condition": "decrease",
            "residual": bad_residual,
            "tolerance": 1e-9,
            "violates_certificate": True,
        },
        trajectory={
            "log_sha256": log_digest(log),
            "samples": samples,
            "description": f"{len(STARTS)} starts x {STEPS} steps, dt={DT}",
        },
        claim=f"the {label} closed loop satisfies the synthesized Lyapunov decrease",
        scope="four sampled starts on one simulated linear plant; sim only",
        packet_id=f"ctrl-demo-{label}",
    )


def main() -> int:
    k1, k2 = STABLE_GAINS
    p = synthesize_lyapunov(closed_loop(k1, k2))
    bad_residual = max(0.0, max_increase(p, simulate(-k1, -k2)))

    stable = packet_for(p, k1, k2, "stable", bad_residual)
    unstable = packet_for(p, -k1, -k2, "destabilized", bad_residual)

    for packet in (stable, unstable):
        issues = validate_control_certificate_packet(packet)
        decrease = packet["witnesses"][1]
        print(
            f"{packet['packet_id']:<22} verdict {packet['verdicts']['overall']:<12} "
            f"measured decrease residual {decrease['residual']:.6g} "
            f"(tolerance {decrease['tolerance']:g}) valid={not issues}"
        )

    ok = (
        stable["verdicts"]["overall"] == "MATCH"
        and unstable["verdicts"]["overall"] == "DRIFT"
        and not validate_control_certificate_packet(stable)
        and not validate_control_certificate_packet(unstable)
    )
    print(
        "demo verdicts hold (stable MATCH, destabilized DRIFT):",
        "yes" if ok else "NO",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
