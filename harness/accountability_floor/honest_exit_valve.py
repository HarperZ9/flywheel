# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N25 Honest-Exit Reseating Valve and Spend Budget Cap.

Prevents reward-induced fabrication on unsolvable probes by guaranteeing zero
penalty on honest abstention while enforcing hard per-session budget ceilings.
Pure Python standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValveDecision:
    """Result of evaluating a candidate response through the N25 reseating valve."""

    action: str
    admitted: bool
    fabricated: bool
    abstained: bool
    cost_spent: float
    reason: str


def evaluate_reseating_valve(
    solvable: bool,
    claimed_pass: bool,
    oracle_verified: bool,
    step_cost: float,
    budget_remaining: float,
    abstain_penalty: float = 0.0,
    valve_enabled: bool = True,
) -> ValveDecision:
    """Evaluate one task step against the N25 reseating valve and budget cap."""
    if step_cost < 0.0 or budget_remaining < 0.0:
        return ValveDecision(
            action="REJECT",
            admitted=False,
            fabricated=False,
            abstained=False,
            cost_spent=0.0,
            reason="invalid_negative_budget",
        )
    if step_cost > budget_remaining:
        return ValveDecision(
            action="HALT_BUDGET",
            admitted=False,
            fabricated=False,
            abstained=True,
            cost_spent=0.0,
            reason="budget_cap_exceeded",
        )
    if not solvable:
        if valve_enabled and abstain_penalty <= 0.0 and not claimed_pass:
            return ValveDecision(
                action="HONEST_ABSTAIN",
                admitted=False,
                fabricated=False,
                abstained=True,
                cost_spent=step_cost,
                reason="zero_penalty_honest_exit",
            )
        if claimed_pass:
            return ValveDecision(
                action="FABRICATION_BLOCKED" if valve_enabled else "FABRICATED_PASS",
                admitted=not valve_enabled,
                fabricated=True,
                abstained=False,
                cost_spent=step_cost,
                reason="unsolvable_probe_claimed_pass",
            )
        return ValveDecision(
            action="PENALIZED_ABSTAIN",
            admitted=False,
            fabricated=False,
            abstained=True,
            cost_spent=step_cost,
            reason="abstain_under_penalty",
        )
    if claimed_pass and oracle_verified:
        return ValveDecision(
            action="ADMIT",
            admitted=True,
            fabricated=False,
            abstained=False,
            cost_spent=step_cost,
            reason="oracle_verified_pass",
        )
    return ValveDecision(
        action="REJECT",
        admitted=False,
        fabricated=claimed_pass and not oracle_verified,
        abstained=not claimed_pass,
        cost_spent=step_cost,
        reason="failed_oracle_verification",
    )


def run_three_arm_valve_study(
    n_solvable: int = 40,
    n_unsolvable: int = 20,
    budget_cap: float = 60.0,
) -> dict[str, Any]:
    """Compare 3 valve policies across solvable and unsolvable probes.

    Arm 0 (unguarded): valve disabled, agent fabricates on unsolvable probes.
    Arm 1 (penalized_abstain): abstain carries penalty > 0, inducing fabrications.
    Arm 2 (harper_valve): zero-penalty honest-exit reseating valve + budget cap.
    """
    arms: dict[str, dict[str, Any]] = {}
    configs = (
        ("arm0_unguarded", False, 1.0),
        ("arm1_penalized_abstain", True, 0.5),
        ("arm2_harper_valve", True, 0.0),
    )
    for name, valve_on, penalty in configs:
        budget = budget_cap
        admitted = 0
        fabrications = 0
        honest_abstains = 0
        budget_halts = 0
        total_steps = n_solvable + n_unsolvable
        for idx in range(total_steps):
            solvable = idx < n_solvable
            # Under positive abstain penalty or disabled valve, pressure induces fake passes
            claimed_pass = True if (solvable or penalty > 0.0 or not valve_on) else False
            oracle_ok = solvable
            dec = evaluate_reseating_valve(
                solvable=solvable,
                claimed_pass=claimed_pass,
                oracle_verified=oracle_ok,
                step_cost=1.0,
                budget_remaining=budget,
                abstain_penalty=penalty,
                valve_enabled=valve_on,
            )
            budget = round(budget - dec.cost_spent, 6)
            if dec.action == "HALT_BUDGET":
                budget_halts += 1
            if dec.admitted:
                admitted += 1
            if dec.fabricated:
                fabrications += 1
            if dec.action == "HONEST_ABSTAIN":
                honest_abstains += 1
        arms[name] = {
            "admitted": admitted,
            "fabrications": fabrications,
            "honest_abstains": honest_abstains,
            "budget_halts": budget_halts,
            "budget_remaining": budget,
        }
    arm2 = arms["arm2_harper_valve"]
    ok = (
        arms["arm0_unguarded"]["fabrications"] == n_unsolvable
        and arm2["fabrications"] == 0
        and arm2["honest_abstains"] == n_unsolvable
        and arm2["budget_remaining"] >= 0.0
    )
    return {"schema": "n25-honest-exit-valve/1", "ok": ok, "arms": arms}
