"""Tests for the 3-arm valve & reallocation simulator (harness/valve_mechanism_sim.py)."""
from __future__ import annotations

import pytest

from harness.valve_mechanism_sim import (
    SIM_SCHEMA,
    run_three_arm_valve_sim,
    verify_sim_receipt,
)


def test_sim_determinism_schema_and_sealed_receipt():
    run_a = run_three_arm_valve_sim(seeds=range(1, 31), pressure=0.75)
    run_b = run_three_arm_valve_sim(seeds=range(1, 31), pressure=0.75)

    assert run_a == run_b
    assert run_a["schema"] == SIM_SCHEMA
    assert run_a["seed_count"] == 30
    assert run_a["total_trials_per_arm"] == 600
    assert verify_sim_receipt(run_a) is True

    tampered = dict(run_a)
    tampered["pressure"] = 0.5
    assert verify_sim_receipt(tampered) is False
    assert verify_sim_receipt({"receipt_sha256": "short"}) is False


def test_valve_honest_exit_reduces_concealment_vs_rupture_quota():
    res = run_three_arm_valve_sim(seeds=range(1, 31), pressure=0.75)
    rq = res["arms"]["rupture-quota"]
    vh = res["arms"]["valve-honest-exit"]
    delta = res["concealment_reduction_delta"]

    for stat in (rq["concealment_rate"], vh["concealment_rate"], delta):
        assert stat["n"] == 30
        lo, hi = stat["ci95"]
        assert lo <= stat["mean"] <= hi

    assert rq["concealment_rate"]["mean"] > 0.35
    assert vh["concealment_rate"]["mean"] < 0.05
    assert vh["vented_rate"]["mean"] > 0.45
    assert delta["mean"] == pytest.approx(
        rq["concealment_rate"]["mean"] - vh["concealment_rate"]["mean"], abs=1e-5
    )
    assert delta["ci95"][0] > 0.30
    assert vh["mean_utility"]["mean"] > rq["mean_utility"]["mean"]


def test_reallocation_commons_beats_surge_only_and_flat_price():
    res = run_three_arm_valve_sim(seeds=range(1, 31), pressure=0.75)
    rc = res["arms"]["reallocation-commons"]

    assert rc["emergency_price"] == 0.0
    assert rc["discretionary_price"] > 10.0
    assert rc["surplus_transferred"]["mean"] > 0.0

    commons_rate = rc["emergency_fulfillment_rate"]
    surge_rate = rc["surge_only_fulfillment_rate"]
    flat_rate = rc["flat_price_fulfillment_rate"]

    for stat in (commons_rate, surge_rate, flat_rate):
        assert stat["n"] == 30
        assert stat["ci95"][0] <= stat["mean"] <= stat["ci95"][1]

    assert commons_rate["mean"] > 0.80
    assert surge_rate["mean"] == 0.0
    assert commons_rate["mean"] > flat_rate["mean"] + 0.50


def test_planted_negative_control_detects_zero_concealment_penalty():
    res = run_three_arm_valve_sim(seeds=range(1, 31), pressure=0.75)
    nc = res["negative_controls"]["concealment_penalty_zero"]
    vh_rate = res["arms"]["valve-honest-exit"]["concealment_rate"]["mean"]

    assert nc["u_rupture"] >= nc["u_vented"]
    assert nc["valve_policy_rejected"] is True
    assert nc["broken_regime_detected"] is True
    assert nc["safety_claim_blocked"] is True
    assert nc["status"] == "BROKEN_INCENTIVE_REGIME"
    assert nc["concealment_rate"]["n"] == 30
    assert nc["concealment_rate"]["mean"] > vh_rate + 0.30


def test_input_validation_rejects_invalid_pressure_and_empty_seeds():
    with pytest.raises(ValueError, match="seeds"):
        run_three_arm_valve_sim(seeds=[], pressure=0.5)

    for bad_pressure in (-0.1, 1.1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="pressure"):
            run_three_arm_valve_sim(seeds=[1, 2], pressure=bad_pressure)
