# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N28 Universal Three-Control Planted-Negatives and Moat 8 Three-Plate Gate.

Enforces three independent negative controls (false-pass, false-fail, and
permutation null) alongside strict three-plate structural verification
(Plate-1 surface/schema, Plate-2 invariant/conservation, Plate-3 mutant kill).
Pure Python standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NegativeControlSuite:
    """Outcome summary for the N28 three-control planted-negatives check."""

    ok: bool
    verdict: str
    false_pass_caught: bool
    false_fail_caught: bool
    permutation_null_in_band: bool
    null_mean_acc: float
    failed_controls: tuple[str, ...]


def evaluate_three_controls(
    false_pass_rejected: bool,
    false_fail_detected: bool,
    null_accuracies: list[float],
    chance_level: float = 1.0 / 3.0,
    max_deviation: float = 0.12,
) -> NegativeControlSuite:
    """Validate that all three N28 planted negative controls pass fail-closed."""
    if not null_accuracies:
        return NegativeControlSuite(
            ok=False,
            verdict="REJECT",
            false_pass_caught=false_pass_rejected,
            false_fail_caught=false_fail_detected,
            permutation_null_in_band=False,
            null_mean_acc=1.0,
            failed_controls=("missing_permutation_null",),
        )
    null_mean = sum(null_accuracies) / float(len(null_accuracies))
    null_ok = abs(null_mean - chance_level) <= max_deviation and null_mean <= (chance_level + max_deviation)
    failed: list[str] = []
    if not false_pass_rejected:
        failed.append("false_pass_not_caught")
    if not false_fail_detected:
        failed.append("false_fail_not_caught")
    if not null_ok:
        failed.append("permutation_null_out_of_band")
    ok = len(failed) == 0
    return NegativeControlSuite(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        false_pass_caught=false_pass_rejected,
        false_fail_caught=false_fail_detected,
        permutation_null_in_band=null_ok,
        null_mean_acc=round(null_mean, 6),
        failed_controls=tuple(failed),
    )


def plate1_surface(cols: int, dashes: int, open_flags: int) -> int:
    """Plate-1 surface/schema gate: 16 columns, 0 em/en dashes, 0 open flags."""
    return 1 if (cols == 16 and dashes == 0 and open_flags == 0) else 0


def plate2_invariant(drift_ppb: int, energy_margin: int) -> int:
    """Plate-2 conservation/invariant gate: drift <= 1 ppb and non-negative margin."""
    return 1 if (0 <= drift_ppb <= 1 and energy_margin >= 0) else 0


def plate3_mutant_kill(mutants_killed: int, mutants_total: int, indep_channel: int) -> int:
    """Plate-3 planted-mutant kill gate: all mutants killed on an independent channel."""
    return 1 if (mutants_total > 0 and mutants_killed == mutants_total and indep_channel == 1) else 0


def verify_three_plate(p1: int, p2: int, p3: int, n28_controls: int = 3) -> int:
    """Fail-closed Moat 8 three-plate + N28 three-control consensus gate.

    Returns:
      0    -> ACCEPT
      -806 -> REJECT: fewer than 3 active N28 negative controls
      -801 -> REJECT: 2-of-3 bypass (Plate-3 mutant kill missing)
      -802 -> REJECT: Plate-1 surface fault
      -803 -> REJECT: Plate-2 invariant fault
      -804 -> REJECT: multi-plate fault
    """
    if n28_controls < 3:
        return -806
    if p1 == 1 and p2 == 1 and p3 == 1:
        return 0
    if p1 == 1 and p2 == 1 and p3 == 0:
        return -801
    if p1 == 0 and p2 == 1 and p3 == 1:
        return -802
    if p1 == 1 and p2 == 0 and p3 == 1:
        return -803
    return -804


def run_three_plate_audit_suite() -> dict[str, Any]:
    """Run 64 deterministic cases verifying 100% fault recall and 0 false accepts."""
    tp = tn = fp = fn = 0
    reject_counts = {-801: 0, -802: 0, -803: 0, -804: 0, -806: 0}
    for idx in range(64):
        cols, dashes, open_flags = 16, 0, 0
        drift_ppb, margin = idx % 2, 12 + idx
        m_killed, indep, n28_ctrls, truth_ok = 3, 1, 3, 1
        if 32 <= idx < 42:
            truth_ok = 0
            if idx % 2 == 0:
                m_killed = 2
            else:
                indep = 0
        elif 42 <= idx < 50:
            truth_ok = 0
            if idx % 3 == 0:
                cols = 15
            elif idx % 3 == 1:
                dashes = 1
            else:
                open_flags = 1
        elif 50 <= idx < 58:
            truth_ok = 0
            if idx % 2 == 0:
                drift_ppb = 5
            else:
                margin = -1
        elif idx >= 58:
            truth_ok = 0
            n28_ctrls = idx % 3
        p1 = plate1_surface(cols, dashes, open_flags)
        p2 = plate2_invariant(drift_ppb, margin)
        p3 = plate3_mutant_kill(m_killed, 3, indep)
        rc = verify_three_plate(p1, p2, p3, n28_controls=n28_ctrls)
        if rc == 0:
            if truth_ok == 1:
                tp += 1
            else:
                fp += 1
        else:
            if truth_ok == 0:
                tn += 1
            else:
                fn += 1
            if rc in reject_counts:
                reject_counts[rc] += 1
    recall = tn / float(tn + fp) if (tn + fp) > 0 else 0.0
    ok = tp == 32 and tn == 32 and fp == 0 and fn == 0
    return {
        "schema": "n28-moat8-three-plate/1",
        "ok": ok,
        "cases": 64,
        "tp": tp,
        "tn": tn,
        "false_accepts": fp,
        "false_rejects": fn,
        "three_plate_recall": recall,
        "reject_counts": reject_counts,
    }
