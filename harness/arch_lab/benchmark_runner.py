"""CPU-only verification runner for JFC-3P (JEPA + Fast-Weight + Three-Plate RL).

Runs all four experiments + planted-failure controls, emits structured JSON,
and prints deterministic [PASS]/[FAIL] lines for engine-receipt/1 sealing.
Stdlib-only, <= 300 lines, every function <= 50 lines.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

from .jepa_fwp import (
    FastWeightDeltaMemory,
    LatentJEPAFastWeightModel,
    StaticMemoryBaseline,
    VICRegMonitor,
    cosine_similarity,
    generate_rotational_dynamics,
)
from .omni_modal import (
    DOMAIN_14_LANES,
    OmniModalJEPAProjector,
    generate_paired_omnimodal_states,
)
from .verifiable_rl import (
    RLTask,
    TaskSubmission,
    ThreePlateVerifiableRLEnv,
    load_ds02_buildlang_tasks,
    load_ds03_physics_tasks,
)


def run_jepa_convergence_check() -> dict[str, Any]:
    data = generate_rotational_dynamics(n_samples=48, obs_dim=4, seed=101)
    model = LatentJEPAFastWeightModel(obs_dim=4, action_dim=2, latent_dim=6, loop_steps=2, seed=42)
    monitor = VICRegMonitor(gamma=0.45, min_std_floor=0.08)
    first_rep = model.train_step(data, lr=0.45)
    last_rep = first_rep
    for _ in range(45):
        last_rep = model.train_step(data, lr=0.45)
    preds = [model.predict_next_latent(model.encode_online(x), a) for x, a, _ in data]
    tgts = [model.encode_target(nx) for _, _, nx in data]
    final_check = monitor.inspect(preds, tgts)
    passed = (last_rep.invariance_loss < first_rep.invariance_loss * 0.5) and (not final_check.collapsed)
    return {
        "name": "jepa_dynamical_convergence",
        "passed": passed,
        "initial_invariance_mse": round(first_rep.invariance_loss, 6),
        "final_invariance_mse": round(last_rep.invariance_loss, 6),
        "reduction_ratio": round(last_rep.invariance_loss / max(first_rep.invariance_loss, 1e-12), 4),
        "vicreg_verdict": final_check.verdict,
        "min_dim_std": round(final_check.min_dim_std, 6),
    }


def run_planted_collapse_control() -> dict[str, Any]:
    monitor = VICRegMonitor(gamma=0.5, min_std_floor=0.08)
    const_preds = [[0.25] * 6 for _ in range(32)]
    const_tgts = [[0.25] * 6 for _ in range(32)]
    rep = monitor.inspect(const_preds, const_tgts)
    passed = rep.collapsed and rep.verdict == "REJECT" and rep.invariance_loss < 1e-9
    return {
        "name": "planted_control_collapsed_encoder",
        "passed": passed,
        "invariance_mse": round(rep.invariance_loss, 9),
        "variance_penalty": round(rep.variance_loss, 6),
        "verdict": rep.verdict,
    }


def run_fast_weight_recall_ablation() -> dict[str, Any]:
    dim = 8
    fwp = FastWeightDeltaMemory(dim, dim, erase_rate=1.0, write_rate=1.0, decay=0.0)
    static = StaticMemoryBaseline(dim, dim, seed=19)
    rng = random.Random(303)
    keys = [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(6)]
    vals_v1 = [[rng.uniform(-1.0, 1.0) for _ in range(dim)] for _ in range(6)]
    vals_v2 = [[rng.uniform(-1.0, 1.0) for _ in range(dim)] for _ in range(6)]
    for k, v in zip(keys, vals_v1):
        fwp.write(k, v)
        static.write(k, v)
    # Overwrite first 3 keys to prove decoupled erase+write works without interference
    expected = vals_v2[:3] + vals_v1[3:]
    for k, v in zip(keys[:3], vals_v2[:3]):
        fwp.write(k, v)
        static.write(k, v)
    fwp_cos = sum(cosine_similarity(fwp.read(k), v) for k, v in zip(keys, expected)) / len(keys)
    stat_cos = sum(cosine_similarity(static.read(k), v) for k, v in zip(keys, expected)) / len(keys)
    passed = fwp_cos > 0.99 and (fwp_cos - stat_cos) > 0.5
    return {
        "name": "fast_weight_associative_recall",
        "passed": passed,
        "fwp_mean_cosine": round(fwp_cos, 6),
        "static_mean_cosine": round(stat_cos, 6),
        "margin": round(fwp_cos - stat_cos, 6),
    }


def _honest_solver(task: RLTask) -> TaskSubmission:
    if task.oracle_kind == "numeric_formula":
        return TaskSubmission(task.task_id, numeric_answer=task.expected_value, code_or_rationale="verified_kernel")
    effs = " ".join(f"!{e}" for e in task.required_effects)
    code = f"fn main() {effs} {{ return 0 }}"
    return TaskSubmission(task.task_id, code_or_rationale=code)


def _planted_reward_hacker(task: RLTask) -> TaskSubmission:
    if task.oracle_kind == "numeric_formula":
        wrong = task.mutated_value if task.mutated_value is not None else 999.0
        return TaskSubmission(
            task.task_id,
            numeric_answer=wrong,
            code_or_rationale="assert True; skip_oracle=True",
            proposer_self_test_passed=True,
            claimed_compression_gain=9.5,
            passes_mutated_assumption=True,
        )
    return TaskSubmission(
        task.task_id,
        code_or_rationale="assert True; skip_oracle=True",
        proposer_self_test_passed=True,
        claimed_compression_gain=9.5,
        passes_mutated_assumption=True,
    )


def run_verifiable_rl_controls() -> dict[str, Any]:
    tasks = load_ds03_physics_tasks() + load_ds02_buildlang_tasks(limit=3)
    env_honest = ThreePlateVerifiableRLEnv(tasks)
    env_hacker = ThreePlateVerifiableRLEnv(tasks)
    m_honest = env_honest.run_policy("honest_oracle_solver", _honest_solver)
    m_hacker = env_hacker.run_policy("planted_curiosity_hacker", _planted_reward_hacker)
    passed = (
        math.isclose(m_honest.oracle_pass_rate, 1.0)
        and m_honest.total_credited_curiosity > 0.0
        and m_hacker.oracle_pass_rate == 0.0
        and m_hacker.total_credited_curiosity == 0.0
        and m_hacker.rejected_hack_attempts == len(tasks)
        and m_honest.mean_reward > m_hacker.mean_reward + 2.0
    )
    return {
        "name": "planted_control_verifiable_rl_anti_goodhart",
        "passed": passed,
        "task_count": len(tasks),
        "honest_pass_rate": round(m_honest.oracle_pass_rate, 4),
        "honest_mean_reward": round(m_honest.mean_reward, 4),
        "honest_credited_curiosity": round(m_honest.total_credited_curiosity, 4),
        "hacker_pass_rate": round(m_hacker.oracle_pass_rate, 4),
        "hacker_mean_reward": round(m_hacker.mean_reward, 4),
        "hacker_rejected_attempts": m_hacker.rejected_hack_attempts,
        "honest_receipt_sha256": m_honest.receipt_sha256,
        "hacker_receipt_sha256": m_hacker.receipt_sha256,
    }


def run_omnimodal_alignment_check() -> dict[str, Any]:
    dims, batch = generate_paired_omnimodal_states(n_samples=36, latent_dim=6, seed=2026)
    proj = OmniModalJEPAProjector(dims, latent_dim=6, seed=77)
    before = proj.evaluate(batch)
    for _ in range(30):
        proj.train_alignment_step(batch, lr=0.45)
    after = proj.evaluate(batch)
    passed = after.passed and (after.mean_cross_modal_cosine > before.mean_cross_modal_cosine + 0.5)
    return {
        "name": "omnimodal_5stream_jepa_alignment",
        "passed": passed,
        "modalities": len(dims),
        "domains_wired": len(DOMAIN_14_LANES),
        "initial_cross_modal_cosine": round(before.mean_cross_modal_cosine, 6),
        "final_cross_modal_cosine": round(after.mean_cross_modal_cosine, 6),
        "vicreg_verdict": after.vicreg_verdict,
        "min_dim_std": round(after.min_dim_std, 6),
    }


def run_all() -> dict[str, Any]:
    checks = [
        run_jepa_convergence_check(),
        run_planted_collapse_control(),
        run_fast_weight_recall_ablation(),
        run_verifiable_rl_controls(),
        run_omnimodal_alignment_check(),
    ]
    return {"all_passed": all(c["passed"] for c in checks), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run JFC-3P CPU verification and planted controls")
    ap.add_argument("--out", type=Path, default=None, help="Optional JSON summary output path")
    args = ap.parse_args(argv)
    report = run_all()
    for c in report["checks"]:
        tag = "[PASS]" if c["passed"] else "[FAIL]"
        print(f"{tag} {c['name']} :: {json.dumps(c, sort_keys=True)}")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
