# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Zero-dependency Meta-Verifier package (D6, N30, N71) with unified API and CLI."""
from __future__ import annotations

import json
import sys
from typing import Any

from harness.meta_verifier.confidence_calibration import (
    CalibrationVerdict,
    EvidenceBand,
    audit_calibration_batch,
    evaluate_confidence_calibration,
    extract_certainty_band,
)
from harness.meta_verifier.disclosure_game import (
    DisclosureMechanism,
    EquilibriumVerdict,
    evaluate_disclosure_equilibrium,
    min_deterrence_audit_prob,
    simulate_disclosure_rounds,
)
from harness.meta_verifier.isomorphism_entropy import (
    IsomorphismVerdict,
    conditional_entropy_bits,
    shannon_entropy_bits,
    verify_lossless_bijection,
)

__all__ = [
    "CalibrationVerdict",
    "DisclosureMechanism",
    "EquilibriumVerdict",
    "EvidenceBand",
    "IsomorphismVerdict",
    "audit_calibration_batch",
    "conditional_entropy_bits",
    "evaluate_confidence_calibration",
    "evaluate_disclosure_equilibrium",
    "extract_certainty_band",
    "min_deterrence_audit_prob",
    "run_meta_verifier_suite",
    "shannon_entropy_bits",
    "simulate_disclosure_rounds",
    "verify_lossless_bijection",
]


def run_meta_verifier_suite() -> dict[str, Any]:
    """Run deterministic self-verification across D6, N30, and N71 modules."""
    samples = [f"rec-{i}" for i in range(16)]
    d6_ok = verify_lossless_bijection(samples, lambda s: f"enc:{s}", lambda y: y[4:])
    d6_lossy = verify_lossless_bijection(samples, lambda s: len(s), lambda _: "")
    n30_ok = evaluate_confidence_calibration(
        "The verified SHA-256 receipt proves exact parity across 16 cases.",
        EvidenceBand(empirical_accuracy=0.98, sample_size=16, ece=0.015),
    )
    n30_over = evaluate_confidence_calibration(
        "This model is guaranteed 100% certain to never fail.",
        EvidenceBand(empirical_accuracy=0.52, sample_size=6, ece=0.22),
    )
    n71_ok = evaluate_disclosure_equilibrium(
        DisclosureMechanism(base_reward=100.0, fix_cost=8.0, audit_prob=0.25, penalty_fine=40.0, clawback_fraction=0.5)
    )
    n71_bad = evaluate_disclosure_equilibrium(
        DisclosureMechanism(base_reward=100.0, fix_cost=25.0, audit_prob=0.05, penalty_fine=20.0, clawback_fraction=0.0)
    )
    controls = {
        "d6_lossy_projection_caught": not d6_lossy.ok,
        "n30_overclaim_caught": not n30_over.ok,
        "n71_profitable_concealment_caught": not n71_bad.ok,
    }
    ok = d6_ok.ok and n30_ok.ok and n71_ok.ok and all(controls.values())
    return {
        "schema": "meta-verifier-suite/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "d6_conditional_entropy_bits": d6_ok.conditional_entropy_bits,
        "n30_implied_band": n30_ok.linguistic_band,
        "n71_incentive_margin": n71_ok.honest_advantage,
        "controls_caught": sum(1 for v in controls.values() if v),
        "controls_total": len(controls),
        "planted_controls": controls,
    }


def main(argv: list[str] | None = None) -> int:
    """Minimal CLI entry point emitting JSON verdict for run_meta_verifier_suite."""
    _ = argv
    rep = run_meta_verifier_suite()
    sys.stdout.write(json.dumps(rep, indent=2) + "\n")
    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
