"""Unit tests and planted-failure controls for Wave 15B NOH-4 & Colab Ablation Runner (CPU-only)."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

from plexus.jfc3p_forge import (
    AVTR4RouteController,
    MetamerPair,
    MetamerSplitRewardScorer,
    NOH4LivingWorldOrganism,
    dense_exact_reverse_kl,
    evaluate_noh4_vs_noh3_vs_flat,
    one_pass_online_reverse_kl,
    run_ablation_a1_metamer_rlvb_armc,
    run_ablation_a3_plato_key,
    run_ablation_a4_avtr_4r,
    run_wave15_colab_ablations,
    verify_forge_receipt,
)

FORGE_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus" / "jfc3p_forge"


def test_noh4_reseating_valve_beats_noh3_and_locks_persistent_nan_and_orth_faults() -> None:
    res = evaluate_noh4_vs_noh3_vs_flat()
    assert res["ok"] is True
    rec = res["transient_recovery"]
    assert rec["noh4_vs_noh3_gain_x"] > 50.0
    assert rec["noh4_post_heal_mse"] < rec["flat_post_heal_mse"]
    assert rec["noh4_readmits"] == 1 and rec["noh3_readmits"] == 0
    assert res["persistent_nan_locked"] is True
    assert res["mace_spread_proactive_caught"] is True

    # Planted orthogonal residual split + Loop-1 Sleep consolidation check.
    org = NOH4LivingWorldOrganism(dim=4, allow_reseat=True, k_settle=3)
    _, diag = org.step([0.0] * 4, 1.0, [[0.1] * 4] * 4, orth_residuals=[0.1, 0.1, 4.5, 0.1])
    assert diag["quarantined"][2] is True
    mem = org.sleep_consolidate([[0.2, -0.1, 0.05, 0.0], [0.2, -0.1, 0.05, 0.0]], loops=3)
    assert all(math.isfinite(v) for v in mem) and mem[0] > 0.1


def test_ablation_a1_one_pass_reverse_kl_metamer_rlvb_and_armc() -> None:
    q = [1.8, -0.4, 0.9, -1.2, 2.3, 0.1, -0.7, 0.5] * 16
    p = [1.4, -0.2, 0.5, -0.9, 1.9, 0.3, -0.5, 0.2] * 16
    assert abs(dense_exact_reverse_kl(q, p) - one_pass_online_reverse_kl(q, p, chunk_size=13)) < 1e-12

    a1 = run_ablation_a1_metamer_rlvb_armc()
    assert a1["ok"] is True
    assert a1["one_pass_kl_abs_err"] < 1e-12
    assert a1["dummy_reward"] == 0.0 and a1["dummy_collapse_rate"] == 1.0
    assert a1["solver_reward"] == 1.0 and a1["rlvb_open_commit_reward"] == 0.0
    assert a1["armc_raw_vs_tool"] == {"raw": 0, "armc": 1}

    pair = MetamerPair("P", "+5", "-5", "5", "-5")
    assert MetamerSplitRewardScorer().score_pair(pair, "5", "-5", belief_open_b=True)["reward"] == 0.0


def test_ablation_a3_plato_key_and_a4_avtr_4r() -> None:
    a3 = run_ablation_a3_plato_key()
    assert a3["ok"] is True
    assert a3["exact_rotation"]["max_abs_err"] < 1e-11
    assert a3["exact_rotation"]["ortho_err"] < 1e-11
    assert a3["planted_shear_max_abs_err"] > 0.5

    a4 = run_ablation_a4_avtr_4r()
    assert a4["ok"] is True
    assert a4["routes"] == ["<direct>", "<imagine>", "<think>", "<imagine_then_think>"]
    assert a4["token_reduction_frac"] > 0.40
    assert AVTR4RouteController().route(0.1, 0.1, belief_ambiguity=0.6)["route"] == "<think>"


def test_wave15_colab_ablation_runner_all_and_receipt_tamper_control(tmp_path: Path) -> None:
    res = run_wave15_colab_ablations(ablation="all", gpu_name="H100", out_dir=tmp_path)
    assert res["ok"] is True
    assert set(res["results"]) == {"A1", "A2", "A3", "A4"}
    assert res["gpu_config"]["gpu_profile"] == "H100-80GB"

    rec = json.loads((tmp_path / "engine_receipt.json").read_text(encoding="utf-8"))
    assert verify_forge_receipt(rec, check_files=True) == (True, [])
    summary = tmp_path / "wave15_ablation_summary.json"
    summary.write_text(summary.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not verify_forge_receipt(rec, check_files=True)[0]


def test_wave15_files_hygiene_and_zero_em_dashes() -> None:
    targets = [FORGE_DIR / "noh4_living_world.py", FORGE_DIR / "wave15_colab_ablation.py", Path(__file__).resolve()]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 300, f"{path.name} exceeds 300 lines: {len(lines)}"
        assert "\u2014" not in text and "\u2013" not in text, f"em/en dash in {path.name}"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{path.name}:{node.name} exceeds 50 lines ({span})"
