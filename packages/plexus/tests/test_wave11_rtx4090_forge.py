"""Unit tests and planted-failure controls for Wave 11 NOH-3 & RTX 4090 Model Forge (CPU-only)."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

from plexus.jfc3p_forge import (
    APACHE2_BASE_MODELS,
    ENV_NAMES,
    FROZEN_DS_HOLDOUTS,
    BuckinghamPiNormalizer,
    NOH3LivingWorldOrganism,
    adapt_colab_gpu_profile,
    build_oracle_training_mix,
    build_rtx4090_serving_spec,
    evaluate_noh3_suite,
    evaluate_oracle_verifiable_suite,
    run_rtx4090_forge,
    verify_forge_receipt,
)

FORGE_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus" / "jfc3p_forge"


def test_noh3_buckingham_pi_kills_raw_ood_spike_and_beats_flat_all_4_envs() -> None:
    suite = evaluate_noh3_suite()
    assert suite["ok"] is True
    assert len(suite["envs"]) == len(ENV_NAMES) == 4
    for row in suite["envs"]:
        assert row["beats_flat_raw"] is True, row
        assert row["beats_flat_adapted"] is True, row
        assert row["noh3_raw_ood_mse"] < row["unnormalized_prior_ood_mse"], row
        assert row["noh3_raw_ood_mse"] < row["flat_ood_mse"], row
        assert row["noh3_adapted_ood_mse"] < row["flat_ood_mse"], row


def test_codit_immune_organ_quarantines_planted_organelle_corruption() -> None:
    org = NOH3LivingWorldOrganism(state_dim=4, action_dim=2)
    norm = BuckinghamPiNormalizer([2.0, 2.0, 1.0, 1.0], [1.0, 1.0])
    s0 = [2.0, -1.0, 0.5, 0.2]
    act = [0.2, -0.1]
    prior = [0.05, 0.02, 0.01, -0.01]

    # Planted NaN corruption in organelle 1.
    out1, d1 = org.predict_next(s0, act, prior, norm, fault_streams={1: [float("nan"), 0.0, 0.0, 0.0]})
    assert all(math.isfinite(v) for v in out1) and d1["quarantined_count"] == 1

    # Planted unit-quaternion norm drift in organelle 2.
    out2, d2 = org.predict_next(s0, act, prior, norm, fault_quats={2: [1.8, 0.0, 0.0, 0.0]})
    assert all(math.isfinite(v) for v in out2) and d2["quarantined_count"] == 2

    # Planted residual explosion in organelle 3.
    out3, d3 = org.predict_next(s0, act, prior, norm, fault_streams={3: [500.0, 0.0, 0.0, 0.0]})
    assert all(math.isfinite(v) for v in out3) and d3["quarantined_count"] == 3
    reasons = [ev.reason for ev in org.immune.events]
    assert any("non_finite" in r for r in reasons)
    assert any("quaternion_norm_drift" in r for r in reasons)
    assert any("pi_norm_explosion" in r for r in reasons)


def test_caustic_carved_sparse_tick_gate_holds_quiet_organelles() -> None:
    org = NOH3LivingWorldOrganism(state_dim=4, action_dim=2, tick_threshold=0.05)
    norm = BuckinghamPiNormalizer([1.0, 1.0, 1.0, 1.0], [1.0, 1.0])
    s0, act, prior = [1.0, 0.5, 0.2, -0.1], [0.1, 0.0], [0.02, -0.01, 0.0, 0.0]
    org.predict_next(s0, act, prior, norm, surprise_pi=0.20)
    for _ in range(5):
        _, diag = org.predict_next(s0, act, prior, norm, surprise_pi=0.001)
    assert org.tick_gate.ticks_held == 5
    assert org.tick_gate.ticks_executed == 1
    assert diag["held_tick_ratio"] > 0.8


def test_colab_gpu_auto_adaptation_and_rtx4090_serving_specs() -> None:
    h100 = adapt_colab_gpu_profile("NVIDIA H100 80GB")
    a100_40 = adapt_colab_gpu_profile("A100-SXM4-40GB")
    l4 = adapt_colab_gpu_profile("NVIDIA L4")
    cpu = adapt_colab_gpu_profile("CPU")
    assert h100["gpu_profile"] == "H100-80GB" and h100["precision"] == "bf16" and h100["lora_rank"] == 64
    assert a100_40["gpu_profile"] == "A100-40GB" and a100_40["grad_checkpointing"] is True
    assert l4["gpu_profile"] == "L4-24GB" and l4["precision"] == "nf4_qlora"
    assert cpu["gpu_profile"] == "CPU-SMOKE"

    for key in APACHE2_BASE_MODELS:
        kv_q = "q4_0" if key == "qwen3.5-35b-a3b" else "q8_0"
        spec = build_rtx4090_serving_spec(key, quant="Q4_K_M", kv_quant=kv_q)
        assert spec["license"] == "Apache-2.0"
        assert spec["fits_rtx4090_24gb"] is True
        assert spec["vram_budget_gb"]["used_gb"] <= 24.0
        assert "--flash-attn" in spec["llama_cpp_flags"]
        assert kv_q in spec["llama_cpp_flags"]
        assert "torch.addmm" in spec["fused_kl_kernel_hint"]
        assert spec["loopcd_speculative_guard"]["loopcd_hidden_r2_allowed"] is False
        assert spec["loopcd_speculative_guard"]["loopcd_logits_omega_max"] == 0.5
        assert "FROM ./" in spec["modelfile"]
    vl_spec = build_rtx4090_serving_spec("qwen2.5-vl-7b", quant="Q4_K_M")
    assert vl_spec["avtr_multimodal_routes"] == ["direct", "imagine", "think", "imagine_then_think"]
    coder_q4 = build_rtx4090_serving_spec("qwen2.5-coder-7b", quant="Q4_K_M")
    assert coder_q4["vram_budget_gb"]["headroom_for_engines_gb"] >= 16.0


def test_alf_latent_feedback_and_loop1_sleep_consolidation() -> None:
    org = NOH3LivingWorldOrganism(state_dim=4, action_dim=2)
    norm = BuckinghamPiNormalizer([1.0, 1.0, 1.0, 1.0], [1.0, 1.0])
    ep = ([1.0, 0.5, 0.2, -0.1], [0.1, 0.0], [1.03, 0.49, 0.21, -0.1], [0.02, -0.01, 0.01, 0.0], norm)
    _, d1 = org.predict_next(ep[0], ep[1], ep[3], norm)
    assert d1["alf_latent_norm"] > 0.0
    sleep = org.sleep_consolidate([ep], passes=3, lr=0.35)
    assert sleep["passes"] == 3 and sleep["updates"] == 3 and sleep["final_pi_mse"] >= 0.0


def test_oracle_training_mix_zero_leak_and_planted_nc_rejection() -> None:
    records = [
        {"license": "Apache-2.0", "prompt": "Write Lean proof", "response": "theorem ok : 1 = 1 := rfl"},
        {"license": "CC-BY-NC-4.0", "prompt": "Non commercial item", "response": "blocked"},
        {"license": "MIT", "prompt": FROZEN_DS_HOLDOUTS["DS-01"][0], "response": "leaked ds01"},
        {"license": "ODC-By-1.0", "prompt": "Clean physics derivation", "response": "E = 0.5 * m * v^2"},
    ]
    mix = build_oracle_training_mix(records)
    assert mix["accepted_count"] == 2
    assert mix["rejected_license"] == 1
    assert mix["rejected_leak"] == 1
    assert mix["zero_leak_verified"] is True


def test_wave11_forge_end_to_end_export_and_receipt_tamper_control(tmp_path: Path) -> None:
    res = run_rtx4090_forge(mode="bench_4090", base_model="qwen2.5-coder-7b", gpu_name="CPU", quant="Q5_K_M", out_dir=tmp_path)
    assert res["ok"] is True
    assert res["verifiable_eval"]["planted_wrong_false_accepts"] == 0
    assert res["verifiable_eval"]["lift"] > 0
    assert (tmp_path / "Modelfile").is_file()
    receipt = json.loads((tmp_path / "engine_receipt.json").read_text(encoding="utf-8"))
    ok, errs = verify_forge_receipt(receipt, check_files=True)
    assert ok and errs == []

    # Planted 1-byte tamper on exported Modelfile must fail closed.
    mf = tmp_path / "Modelfile"
    mf.write_text(mf.read_text(encoding="utf-8") + " ", encoding="utf-8")
    tampered_ok, tampered_errs = verify_forge_receipt(receipt, check_files=True)
    assert not tampered_ok and any("drift" in e for e in tampered_errs)

    eval_trap = evaluate_oracle_verifiable_suite({}, {})
    assert eval_trap["planted_wrong_false_accepts"] == 0


def test_wave11_files_hygiene_and_zero_em_dashes() -> None:
    targets = [
        FORGE_DIR / "noh3_living_world.py",
        FORGE_DIR / "rtx4090_model_forge.py",
        Path(__file__).resolve(),
    ]
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
