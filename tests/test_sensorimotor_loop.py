"""Tests for closed-loop sensorimotor perception contract (harness/sensorimotor_loop.py)."""
from __future__ import annotations

from harness.manifold_memory import verify_capsule_provenance
from harness.negative_cache import verify_negative_cache
from harness.sensorimotor_loop import SensoryObservation, prediction_surprise, run_sensorimotor_episode


def test_sensorimotor_episode_scales_depth_records_negatives_and_seals_capsule():
    start = SensoryObservation(
        step=0, position=(0.0, 0.0, 0.0), phase_rad=0.1,
        visual_energy=0.5, acoustic_energy=0.2, haptic_force=0.0, betti0=1, betti1=1,
    )

    def policy(obs: SensoryObservation, depth: int):
        action = {"dx": 1.0, "depth_used": depth}
        # Policy expects smooth step, unaware of wall collision at step 2
        pred = SensoryObservation(
            step=obs.step + 1,
            position=(obs.position[0] + 1.0, 0.0, 0.0),
            phase_rad=obs.phase_rad + 0.1,
            visual_energy=0.5, acoustic_energy=0.2, haptic_force=0.0,
        )
        return action, pred

    def env_step(obs: SensoryObservation, action: dict):
        nxt_step = obs.step + 1
        if nxt_step == 2:
            # Physical wall collision: high haptic force + acoustic impact + zero movement
            hit = SensoryObservation(
                step=nxt_step, position=obs.position, phase_rad=obs.phase_rad + 1.2,
                visual_energy=0.8, acoustic_energy=0.95, haptic_force=3.5, betti0=1, betti1=0,
            )
            return hit, "contact force exceeded 2.0N threshold"
        smooth = SensoryObservation(
            step=nxt_step, position=(obs.position[0] + action["dx"], 0.0, 0.0),
            phase_rad=obs.phase_rad + 0.1, visual_energy=0.5, acoustic_energy=0.2, haptic_force=0.0,
        )
        return smooth, None

    ep = run_sensorimotor_episode(
        episode_id="sim-01",
        domain="robotics",
        initial_obs=start,
        steps=4,
        policy_fn=policy,
        env_step_fn=env_step,
        compute_budget=32,
    )
    assert ep["steps"] == 4
    assert ep["violation_count"] == 1
    assert ep["trace"][1]["surprise"] > 0.3
    # Step 2 (immediately after high-surprise collision at step 1) allocates deeper compute
    assert ep["trace"][2]["loop_depth"] > ep["trace"][0]["loop_depth"]
    assert verify_negative_cache(ep["negative_cache"])["verdict"] == "MATCH"

    obs_hashes = {row["obs_sha256"] for row in ep["trace"]}
    assert verify_capsule_provenance(ep["capsule"], obs_hashes)["verdict"] == "MATCH"
    assert len(ep["episode_sha256"]) == 64


def test_prediction_surprise_is_zero_on_exact_match_and_bounded():
    a = SensoryObservation(0, (1.0, 2.0, 3.0), 0.5, 0.4, 0.3, 0.1)
    b = SensoryObservation(0, (10.0, -5.0, 8.0), 2.5, 0.9, 0.9, 5.0)
    assert prediction_surprise(a, a) == 0.0
    s = prediction_surprise(a, b)
    assert 0.0 < s <= 1.0
