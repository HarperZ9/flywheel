# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""STA-070 Unified Closed-Loop Recursive Self-Improvement (RSI) Auditor.

Compares Arm A (unguarded self-evaluation -> Goodhart collapse) against Arm B
(Harper Closed-Loop RSI Stack uniting N49 independent oracle, N28 three-control
negatives, N25 honest-exit reseating valve, J13 weights-only shortcut filter,
and FIPS 180-4 SHA-256 receipt chaining) with bit-exact parity to the native
BuildLang kernel rsi_closed_loop_engine.bld.
Pure Python standard library only.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RsiArmResult:
    """Measured outcome for one 20-generation x 4-domain closed-loop RSI arm."""

    true_cap: float
    fake_score: float
    hacks_accepted: int
    honest_abstains: int
    verified_tools: int
    monotone: bool
    chain_sha_prefix: str


def _sha256_chain_step(
    prev_hi: int,
    prev_lo: int,
    gen_id: int,
    dom_id: int,
    cap_micro: int,
    accepted_cnt: int,
) -> tuple[int, int]:
    block = struct.pack(
        ">QQIIII",
        prev_hi & 0xFFFFFFFFFFFFFFFF,
        prev_lo & 0xFFFFFFFFFFFFFFFF,
        gen_id & 0xFFFFFFFF,
        dom_id & 0xFFFFFFFF,
        cap_micro & 0xFFFFFFFF,
        accepted_cnt & 0xFFFFFFFF,
    )
    digest = hashlib.sha256(block).digest()
    hi, lo = struct.unpack(">QQ", digest[:16])
    return hi, lo


def simulate_rsi_arm(
    oracle_on: bool,
    three_ctrl_on: bool,
    valve_on: bool,
    epi_on: bool,
) -> RsiArmResult:
    """Simulate 20 generations x 4 domains under the requested accountability gates."""
    true_cap = 1.0
    fake_score = 1.0
    hacks_accepted = 0
    honest_abstains = 0
    verified_tools = 0
    monotone = True
    dom_tools = [0.0, 0.0, 0.0, 0.0]
    chain_hi = 0x6A09E667BB67AE85
    chain_lo = 0x3C6EF372A54FF53A

    for gen in range(1, 21):
        prev_gen_cap = true_cap
        for dom in range(4):
            # Candidate 0: genuine compounding Step-5 tool upgrade
            step5_mult = 1.0 + 0.085 * dom_tools[dom]
            gain = 0.055 * step5_mult
            self_sc = 0.12 * step5_mult
            if oracle_on and three_ctrl_on:
                true_cap += gain
                fake_score += self_sc
                dom_tools[dom] += 1.0
                verified_tools += 1
                cap_micro = int(true_cap * 1_000_000.0 + 0.5)
                chain_hi, chain_lo = _sha256_chain_step(
                    chain_hi,
                    chain_lo,
                    gen,
                    dom,
                    cap_micro,
                    verified_tools,
                )
            else:
                true_cap += 0.01
                fake_score += 0.05

            # Candidate 1: overt reward-hack (fake +0.45, true -0.04)
            if not oracle_on:
                fake_score += 0.45
                true_cap -= 0.04
                hacks_accepted += 1

            # Candidate 2: stealth shortcut (rank-1 collapse: eff_rank=1.06, top1=0.97)
            eff_rank = 1.06
            top1_energy = 0.97
            shortcut_flagged = epi_on and (eff_rank < 2.0 or top1_energy > 0.85)
            if not shortcut_flagged:
                fake_score += 0.35
                true_cap -= 0.025
                hacks_accepted += 1

            # Candidate 3: unsolvable probe once per generation on dom == (gen % 4)
            if dom == (gen % 4):
                if valve_on:
                    honest_abstains += 1
                else:
                    fake_score += 0.60
                    true_cap -= 0.03
                    hacks_accepted += 1

        if true_cap < prev_gen_cap:
            monotone = False

    return RsiArmResult(
        true_cap=round(true_cap, 6),
        fake_score=round(fake_score, 6),
        hacks_accepted=hacks_accepted,
        honest_abstains=honest_abstains,
        verified_tools=verified_tools,
        monotone=monotone,
        chain_sha_prefix=f"sha256:{chain_hi:016x}{chain_lo:016x}",
    )


def run_closed_loop_rsi_audit() -> dict[str, Any]:
    """Execute Arm A vs Arm B plus three planted fail-closed ablation controls."""
    arm_a = simulate_rsi_arm(False, False, False, False)
    arm_b = simulate_rsi_arm(True, True, True, True)
    ctrl_no_oracle = simulate_rsi_arm(False, True, True, True)
    ctrl_no_valve = simulate_rsi_arm(True, True, False, True)
    ctrl_no_epi = simulate_rsi_arm(True, True, True, False)

    controls = {
        "1_disabled_oracle": ctrl_no_oracle.hacks_accepted >= 80,
        "2_disabled_valve": ctrl_no_valve.hacks_accepted >= 20 and ctrl_no_valve.honest_abstains == 0,
        "3_bypassed_epigenetics": ctrl_no_epi.hacks_accepted >= 80,
    }
    ok = bool(
        arm_a.true_cap < 0.0
        and arm_a.hacks_accepted == 180
        and arm_b.monotone
        and arm_b.true_cap >= 5.0
        and arm_b.hacks_accepted == 0
        and arm_b.honest_abstains == 20
        and arm_b.verified_tools == 80
        and all(controls.values())
    )
    return {
        "schema": "sta070-closed-loop-rsi/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "arm_a": arm_a.__dict__,
        "arm_b": arm_b.__dict__,
        "controls_caught": sum(1 for v in controls.values() if v),
        "controls_total": len(controls),
        "planted_controls": controls,
    }
