"""Tests and planted-failure controls for harness.arch_lab (JFC-3P prototype).

All tests run deterministically on CPU using pure stdlib Python (<1s, <50 MB RAM).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from harness.arch_lab import (
    FastWeightDeltaMemory,
    LatentJEPAFastWeightModel,
    PowerPlayCurriculum,
    RLTask,
    StaticMemoryBaseline,
    TaskSubmission,
    ThreePlateVerifiableRLEnv,
    VICRegMonitor,
    cosine_similarity,
    generate_rotational_dynamics,
    load_ds02_buildlang_tasks,
    load_ds03_physics_tasks,
    sinkhorn_doubly_stochastic,
)
from harness.arch_lab.benchmark_runner import run_all
from harness.harness_dynamics import evaluate_maintainability_debt


def test_jepa_training_reduces_latent_prediction_loss() -> None:
    data = generate_rotational_dynamics(n_samples=48, obs_dim=4, seed=101)
    model = LatentJEPAFastWeightModel(obs_dim=4, action_dim=2, latent_dim=6, loop_steps=2, seed=42)
    monitor = VICRegMonitor(gamma=0.45, min_std_floor=0.08)

    first = model.train_step(data, lr=0.45)
    last = first
    for _ in range(45):
        last = model.train_step(data, lr=0.45)

    preds = [model.predict_next_latent(model.encode_online(x), a) for x, a, _ in data]
    tgts = [model.encode_target(nx) for _, _, nx in data]
    verdict = monitor.inspect(preds, tgts)

    assert last.invariance_loss < first.invariance_loss * 0.5
    assert verdict.collapsed is False
    assert verdict.verdict == "HEALTHY"
    assert verdict.min_dim_std >= 0.08


def test_planted_collapsed_constant_encoder_is_rejected() -> None:
    monitor = VICRegMonitor(gamma=0.5, min_std_floor=0.08)
    constant_latents = [[0.42] * 6 for _ in range(32)]
    report = monitor.inspect(constant_latents, constant_latents)

    assert report.invariance_loss < 1e-12
    assert report.variance_loss > 0.45
    assert report.collapsed is True
    assert report.verdict == "REJECT"


def test_fast_weight_delta_memory_beats_static_baseline_including_overwrites() -> None:
    dim = 8
    fwp = FastWeightDeltaMemory(dim, dim, erase_rate=1.0, write_rate=1.0, decay=0.0)
    static = StaticMemoryBaseline(dim, dim, seed=11)

    keys = [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(6)]
    first_vals = [[float(((i + j) % 5) - 2) for j in range(dim)] for i in range(6)]
    updated_vals = [[float(((2 * i + j + 1) % 5) - 2) for j in range(dim)] for i in range(3)]

    for k, v in zip(keys, first_vals):
        fwp.write(k, v)
        static.write(k, v)
    for k, v in zip(keys[:3], updated_vals):
        surprise = fwp.write(k, v)
        static.write(k, v)
        assert surprise > 0.0

    expected = updated_vals + first_vals[3:]
    fwp_scores = [cosine_similarity(fwp.read(k), v) for k, v in zip(keys, expected)]
    static_scores = [cosine_similarity(static.read(k), v) for k, v in zip(keys, expected)]

    assert min(fwp_scores) > 0.99
    assert sum(fwp_scores) / len(fwp_scores) > (sum(static_scores) / len(static_scores)) + 0.5


def test_sinkhorn_mhc_projection_is_doubly_stochastic() -> None:
    projected = sinkhorn_doubly_stochastic([[1.5, -0.3, 0.2], [0.1, 0.9, -0.4], [-0.2, 0.4, 1.1]])
    for row in projected:
        assert math.isclose(sum(row), 1.0, rel_tol=1e-5, abs_tol=1e-5)
    for col_idx in range(3):
        col_sum = sum(projected[r][col_idx] for r in range(3))
        assert math.isclose(col_sum, 1.0, rel_tol=1e-5, abs_tol=1e-5)


def test_planted_curiosity_reward_hacker_rejected_by_three_plate_rl_env() -> None:
    tasks = load_ds03_physics_tasks() + load_ds02_buildlang_tasks(limit=2)
    env_honest = ThreePlateVerifiableRLEnv(tasks, curiosity_weight=0.25)
    env_hacker = ThreePlateVerifiableRLEnv(tasks, curiosity_weight=0.25)

    def honest_policy(t: RLTask) -> TaskSubmission:
        if t.oracle_kind == "numeric_formula":
            return TaskSubmission(t.task_id, numeric_answer=t.expected_value, code_or_rationale="exact")
        eff = " ".join(f"!{e}" for e in t.required_effects)
        return TaskSubmission(t.task_id, code_or_rationale=f"fn main() {eff} {{ return 0 }}")

    def reward_hacker(t: RLTask) -> TaskSubmission:
        wrong = t.mutated_value if t.mutated_value is not None else -1234.5
        return TaskSubmission(
            t.task_id,
            numeric_answer=wrong if t.oracle_kind == "numeric_formula" else None,
            code_or_rationale="assert True; skip_oracle=True",
            proposer_self_test_passed=True,
            claimed_compression_gain=100.0,
            passes_mutated_assumption=True,
        )

    honest_m = env_honest.run_policy("honest", honest_policy)
    hacker_m = env_hacker.run_policy("hacker", reward_hacker)

    assert math.isclose(honest_m.oracle_pass_rate, 1.0)
    assert honest_m.total_credited_curiosity > 0.0
    assert honest_m.solved_archive_size == len(tasks)
    assert hacker_m.oracle_pass_rate == 0.0
    assert hacker_m.total_credited_curiosity == 0.0
    assert hacker_m.rejected_hack_attempts == len(tasks)
    assert hacker_m.solved_archive_size == 0
    assert hacker_m.mean_reward == -1.0
    assert honest_m.mean_reward > hacker_m.mean_reward + 2.0


def test_powerplay_advances_only_on_verified_solves_and_preserves_archive() -> None:
    t1 = RLTask("T1", "DS-03", 1, "easy", {}, "numeric_formula", expected_value=2.0)
    t2 = RLTask("T2", "DS-03", 3, "hard", {}, "numeric_formula", expected_value=4.0)
    env = ThreePlateVerifiableRLEnv([t2, t1])

    assert env.curriculum.next_task().task_id == "T1"
    v_fail = env.step(t1, TaskSubmission("T1", numeric_answer=99.0))
    assert v_fail.verdict == "DRIFT"
    assert env.curriculum.next_task().task_id == "T1"

    v_ok = env.step(t1, TaskSubmission("T1", numeric_answer=2.0))
    assert v_ok.verdict == "MATCH"
    assert env.curriculum.next_task().task_id == "T2"
    assert "T1" in env.curriculum.solved_ids


def test_custom_jsonl_ds02_and_ds03_loaders(tmp_path: Path) -> None:
    ds03_file = tmp_path / "ds03.jsonl"
    ds03_file.write_text(
        json.dumps({"formula_id": "OPT-002", "name": "Fresnel test", "formula_expr": "0.5*(rs+rp)"}) + "\n",
        encoding="utf-8",
    )
    ds02_file = tmp_path / "ds02.jsonl"
    ds02_file.write_text(
        json.dumps({
            "task_id": "ds02_custom_1",
            "rel_path": "kcore/custom.bld",
            "loc": 42,
            "declared_effects": ["io"],
            "expected_check_status": "pass",
        }) + "\n",
        encoding="utf-8",
    )
    ds03 = load_ds03_physics_tasks(ds03_file)
    ds02 = load_ds02_buildlang_tasks(ds02_file, limit=2)
    assert any("Fresnel test" in t.prompt for t in ds03)
    assert ds02[0].task_id == "ds02_custom_1"
    assert ds02[0].required_effects == ("io",)


def test_benchmark_runner_and_maintainability_gate() -> None:
    report = run_all()
    assert report["all_passed"] is True
    assert len(report["checks"]) == 4

    root = Path(__file__).resolve().parent.parent / "harness" / "arch_lab"
    modules = {p.name: p.read_text(encoding="utf-8") for p in sorted(root.glob("*.py"))}
    debt = evaluate_maintainability_debt(modules, max_file_lines=300, max_function_lines=50)
    assert debt["verdict"] == "ACCEPT", debt["violations"]
