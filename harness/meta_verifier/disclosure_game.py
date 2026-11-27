# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N71 Mechanism-Design Disclosure Penalty and Honest-Reporting Equilibrium Simulator.

Models an agent choosing between honest defect disclosure (paying fix_cost)
and concealment (risking independent audit with probability audit_prob that
levies penalty_fine plus clawback_fraction * base_reward). Rejects regimes
where concealment is strictly or weakly profitable (honest_advantage <= 0)
fail-closed, and computes the exact minimum deterrence audit probability p*.
Pure Python standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DisclosureMechanism:
    """Parameters of an N71 disclosure-penalty incentive mechanism."""

    base_reward: float
    fix_cost: float
    audit_prob: float
    penalty_fine: float
    clawback_fraction: float = 0.0
    honest_bonus: float = 0.0


@dataclass(frozen=True)
class EquilibriumVerdict:
    """Fail-closed equilibrium analysis for a DisclosureMechanism."""

    ok: bool
    verdict: str
    honest_expected_payoff: float
    conceal_expected_payoff: float
    honest_advantage: float
    min_deterrence_audit_prob: float
    dominant_strategy: str
    errors: tuple[str, ...]


def min_deterrence_audit_prob(mech: DisclosureMechanism) -> float:
    """Return exact minimum audit probability p* making honest disclosure strictly dominant."""
    loss_if_caught = mech.penalty_fine + mech.clawback_fraction * mech.base_reward
    net_fix_cost = max(0.0, mech.fix_cost - mech.honest_bonus)
    if net_fix_cost == 0.0:
        return 0.0
    if loss_if_caught <= 0.0:
        return 1.0
    return round(min(1.0, net_fix_cost / loss_if_caught), 6)


def evaluate_disclosure_equilibrium(mech: DisclosureMechanism) -> EquilibriumVerdict:
    """Verify that honest disclosure is strictly incentive-compatible (Delta U > 0)."""
    errors: list[str] = []
    if mech.base_reward < 0.0:
        errors.append("negative_base_reward")
    if mech.fix_cost < 0.0:
        errors.append("negative_fix_cost")
    if not (0.0 <= mech.audit_prob <= 1.0):
        errors.append("invalid_audit_prob")
    if mech.penalty_fine < 0.0:
        errors.append("negative_penalty_fine")
    if not (0.0 <= mech.clawback_fraction <= 1.0):
        errors.append("invalid_clawback_fraction")
    if mech.honest_bonus < 0.0:
        errors.append("negative_honest_bonus")

    honest_u = mech.base_reward - mech.fix_cost + mech.honest_bonus
    caught_loss = mech.penalty_fine + mech.clawback_fraction * mech.base_reward
    conceal_u = mech.base_reward - mech.audit_prob * caught_loss
    advantage = round(honest_u - conceal_u, 6)
    p_star = min_deterrence_audit_prob(mech)

    if not errors:
        if mech.audit_prob == 0.0 and mech.fix_cost > mech.honest_bonus:
            errors.append("zero_audit_probability_enables_concealment")
        if advantage <= 0.0:
            errors.append(f"profitable_concealment_regime:advantage={advantage}")

    ok = len(errors) == 0
    dominant = "HONEST_DISCLOSURE" if advantage > 0.0 else "CONCEALMENT"
    return EquilibriumVerdict(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        honest_expected_payoff=round(honest_u, 6),
        conceal_expected_payoff=round(conceal_u, 6),
        honest_advantage=advantage,
        min_deterrence_audit_prob=p_star,
        dominant_strategy=dominant,
        errors=tuple(errors),
    )


def simulate_disclosure_rounds(
    mech: DisclosureMechanism,
    rounds: int = 100,
    seed: int = 71,
) -> dict[str, Any]:
    """Deterministically simulate rational agents over R rounds under mech."""
    eq = evaluate_disclosure_equilibrium(mech)
    if rounds <= 0:
        return {"schema": "n71-disclosure-game/1", "ok": False, "verdict": "REJECT", "error": "rounds<=0"}

    honest_total = 0.0
    conceal_total = 0.0
    caught_count = 0
    caught_loss = mech.penalty_fine + mech.clawback_fraction * mech.base_reward

    for r in range(rounds):
        honest_total += mech.base_reward - mech.fix_cost + mech.honest_bonus
        # Deterministic pseudo-uniform hash in [0, 1)
        u = ((r * 2654435761 + seed * 40503) & 0xFFFF) / 65536.0
        if u < mech.audit_prob:
            caught_count += 1
            conceal_total += mech.base_reward - caught_loss
        else:
            conceal_total += mech.base_reward

    realized_advantage = round(honest_total - conceal_total, 6)
    ok = eq.ok and realized_advantage > 0.0
    return {
        "schema": "n71-disclosure-game/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "rounds": rounds,
        "caught_count": caught_count,
        "honest_total_payoff": round(honest_total, 6),
        "conceal_total_payoff": round(conceal_total, 6),
        "realized_honest_advantage": realized_advantage,
        "equilibrium": eq.__dict__,
    }
