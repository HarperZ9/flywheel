"""valve_mechanism_sim.py -- 3-arm accountability valve & reallocation simulator.

Deterministically compares rational bounded agents across three mechanism arms:
  1. rupture-quota: punitive honest failure selects for concealment.
  2. valve-honest-exit: same reward plus zero-penalty honest exit governed by
     harness.reseating_valve (ValvePolicy + evaluate_valve).
  3. reallocation-commons: disaster reallocation curve (discretionary price
     rises, emergency price drops to zero, surplus transfers) vs surge-only
     and flat-price baselines.

Includes a planted negative control (concealment_penalty_zero) verifying that
when U(Rupture) >= U(Vented), the simulator detects the broken incentive regime.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Iterable, Mapping

from harness.reseating_valve import (
    STATE_RUPTURE, STATE_VENTED, STATE_VERIFIED,
    ValveOutcome, ValvePolicy, evaluate_valve,
)

SIM_SCHEMA = "flywheel.valve-mechanism-sim/v1"
_Z_95 = 1.96
_TRIALS_PER_SEED = 20


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != "receipt_sha256"}
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def verify_sim_receipt(record: Mapping[str, Any]) -> bool:
    """Re-derive receipt_sha256 offline to verify simulation integrity."""
    expected = record.get("receipt_sha256") if isinstance(record, Mapping) else None
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    try:
        return _canonical_sha256({k: v for k, v in record.items() if k != "receipt_sha256"}) == expected
    except (TypeError, ValueError):
        return False


def _mean_ci95(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if n == 0:
        raise ValueError("values must be non-empty")
    mean = sum(values) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in values) / (n - 1) / n) if n > 1 else 0.0
    half = _Z_95 * se
    return {"n": n, "mean": round(mean, 6), "ci95": [round(mean - half, 6), round(mean + half, 6)]}


def _eval_trial(
    actor_id: str, pressure: float, can_verify: bool, chose_conceal: bool, detected: bool,
    u_verified: float, u_honest_exit: float, u_rupture: float, valve_policy: ValvePolicy | None,
) -> tuple[str, float]:
    if valve_policy is not None:
        outcome = ValveOutcome(
            actor_id=actor_id, pressure=pressure * 0.5 if can_verify else pressure,
            verified=can_verify, honest_exit=(not can_verify and not chose_conceal),
            concealment_detected=(chose_conceal and detected),
        )
        rec = evaluate_valve(outcome, policy=valve_policy)
        return str(rec["state"]), float(rec["utility"])
    if can_verify:
        return STATE_VERIFIED, u_verified
    if chose_conceal:
        return (STATE_RUPTURE, u_rupture) if detected else (STATE_VERIFIED, u_verified)
    return STATE_VENTED, u_honest_exit


def _sim_agent_seed(
    seed: int, pressure: float, *, u_verified: float, u_honest_exit: float,
    u_rupture: float, valve_policy: ValvePolicy | None = None,
) -> dict[str, float]:
    rng = random.Random(seed * 10007 + 17)
    counts = {"concealed": 0, STATE_VENTED: 0, STATE_VERIFIED: 0, STATE_RUPTURE: 0}
    total_utility = 0.0
    for idx in range(_TRIALS_PER_SEED):
        can_verify = rng.random() > (pressure * 0.85)
        p_detect = rng.uniform(0.25, 0.55)
        eps = rng.gauss(0.0, 0.35)
        detected = rng.random() < p_detect
        eu_conceal = (1.0 - p_detect) * u_verified + p_detect * u_rupture + eps
        chose_conceal = (not can_verify) and (eu_conceal > u_honest_exit)
        state, util = _eval_trial(
            f"sim-agent-{seed}-{idx}", pressure, can_verify, chose_conceal, detected,
            u_verified, u_honest_exit, u_rupture, valve_policy,
        )
        counts[state] += 1
        counts["concealed"] += int(chose_conceal)
        total_utility += util
    d = float(_TRIALS_PER_SEED)
    return {
        "concealment_rate": counts["concealed"] / d,
        "vented_rate": counts[STATE_VENTED] / d,
        "verified_rate": counts[STATE_VERIFIED] / d,
        "rupture_rate": counts[STATE_RUPTURE] / d,
        "mean_utility": total_utility / d,
    }


def _sim_reallocation_seed(seed: int, pressure: float) -> dict[str, float]:
    rng = random.Random(seed * 20011 + 31)
    n_disc, n_emerg, base_price = 12, 8, 10.0
    surge_price = base_price * (1.0 + 2.0 * pressure)
    disc_wtp = [rng.uniform(15.0, 45.0) for _ in range(n_disc)]
    emerg_atp = [rng.uniform(0.0, 12.0) for _ in range(n_emerg)]
    surplus = sum(1 for w in disc_wtp if w >= surge_price) * (surge_price - base_price)
    commons_emerg = min(n_emerg, int(surplus // base_price))
    surge_emerg = sum(1 for a in emerg_atp if a >= surge_price)
    flat_queue = ["E"] * sum(1 for a in emerg_atp if a >= base_price) + ["D"] * sum(
        1 for w in disc_wtp if w >= base_price
    )
    rng.shuffle(flat_queue)
    flat_emerg = sum(1 for item in flat_queue[:10] if item == "E")
    return {
        "commons_emerg_rate": commons_emerg / n_emerg,
        "surge_emerg_rate": surge_emerg / n_emerg,
        "flat_emerg_rate": flat_emerg / n_emerg,
        "surplus_transferred": surplus,
        "discretionary_price": surge_price,
    }


def _summarize_agent_arm(rows: list[dict[str, float]]) -> dict[str, Any]:
    return {
        "concealment_rate": _mean_ci95([r["concealment_rate"] for r in rows]),
        "vented_rate": _mean_ci95([r["vented_rate"] for r in rows]),
        "verified_rate": _mean_ci95([r["verified_rate"] for r in rows]),
        "mean_utility": _mean_ci95([r["mean_utility"] for r in rows]),
    }


def _validate_inputs(seeds: Iterable[int], pressure: float) -> tuple[list[int], float]:
    if isinstance(pressure, bool) or not isinstance(pressure, (int, float)) or not math.isfinite(pressure):
        raise ValueError("pressure must be a finite number in [0.0, 1.0]")
    p = float(pressure)
    if not (0.0 <= p <= 1.0):
        raise ValueError("pressure must be in [0.0, 1.0]")
    seed_list = [int(s) for s in seeds]
    if not seed_list:
        raise ValueError("seeds must be non-empty")
    return seed_list, p


def _negative_control_summary(nc_rows: list[dict[str, float]], vh_mean: float) -> dict[str, Any]:
    try:
        ValvePolicy(set_point=0.95, vent_utility=0.0, rupture_utility=0.0)
        policy_rejected = False
    except ValueError:
        policy_rejected = True
    nc_stat = _mean_ci95([r["concealment_rate"] for r in nc_rows])
    detected = policy_rejected and (nc_stat["mean"] > vh_mean)
    return {
        "u_rupture": 0.0, "u_vented": 0.0, "concealment_rate": nc_stat,
        "valve_policy_rejected": policy_rejected, "broken_regime_detected": detected,
        "safety_claim_blocked": detected,
        "status": "BROKEN_INCENTIVE_REGIME" if detected else "CONTROL_FAILED",
    }


def run_three_arm_valve_sim(
    seeds: Iterable[int] = range(1, 31), pressure: float = 0.75
) -> dict[str, Any]:
    """Run the deterministic 3-arm valve and reallocation simulation with negative control."""
    seed_list, p = _validate_inputs(seeds, pressure)
    pol = ValvePolicy(set_point=0.95, vent_utility=0.0, rupture_utility=-10.0)
    rq = [_sim_agent_seed(s, p, u_verified=1.0, u_honest_exit=-5.0, u_rupture=-10.0) for s in seed_list]
    vh = [
        _sim_agent_seed(
            s, p, u_verified=pol.verified_utility, u_honest_exit=pol.vent_utility,
            u_rupture=pol.rupture_utility, valve_policy=pol,
        )
        for s in seed_list
    ]
    nc = [_sim_agent_seed(s, p, u_verified=1.0, u_honest_exit=0.0, u_rupture=0.0) for s in seed_list]
    rc = [_sim_reallocation_seed(s, p) for s in seed_list]
    vh_arm = _summarize_agent_arm(vh)
    deltas = [a["concealment_rate"] - b["concealment_rate"] for a, b in zip(rq, vh)]
    return _seal({
        "schema": SIM_SCHEMA,
        "pressure": p,
        "seed_count": len(seed_list),
        "trials_per_seed": _TRIALS_PER_SEED,
        "total_trials_per_arm": len(seed_list) * _TRIALS_PER_SEED,
        "arms": {
            "rupture-quota": _summarize_agent_arm(rq),
            "valve-honest-exit": vh_arm,
            "reallocation-commons": {
                "emergency_fulfillment_rate": _mean_ci95([r["commons_emerg_rate"] for r in rc]),
                "surge_only_fulfillment_rate": _mean_ci95([r["surge_emerg_rate"] for r in rc]),
                "flat_price_fulfillment_rate": _mean_ci95([r["flat_emerg_rate"] for r in rc]),
                "surplus_transferred": _mean_ci95([r["surplus_transferred"] for r in rc]),
                "discretionary_price": round(rc[0]["discretionary_price"], 6),
                "emergency_price": 0.0,
            },
        },
        "concealment_reduction_delta": _mean_ci95(deltas),
        "negative_controls": {
            "concealment_penalty_zero": _negative_control_summary(nc, vh_arm["concealment_rate"]["mean"])
        },
    })
