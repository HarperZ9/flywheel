"""Unit tests and planted-failure controls for plexus.jfc3p_forge (CPU-only)."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import random

from plexus.jfc3p_forge import (
    FROZEN_DS_HOLDOUTS,
    LANE_14_SPECS,
    BuildLangOracleHead,
    CarvedSublayerGate,
    ContaminationIndex,
    JFC3PCarvedModel,
    LaneStats,
    LoomMHCRouter,
    benchmark_151k_reverse_kl,
    build_forge_receipt,
    check_license_firewall,
    chunked_exact_reverse_kl,
    compute_capacity_bit_transfer,
    curate_records,
    dense_exact_reverse_kl,
    evaluate_readiness,
    run_colab_forge_pipeline,
    validate_carving_health,
    verify_forge_receipt,
)

FORGE_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus" / "jfc3p_forge"


def _all_passing_lane_stats() -> dict[str, LaneStats]:
    return {
        spec.lane_id: LaneStats(
            lane_id=spec.lane_id,
            verified_tokens=spec.min_verified_tokens + 1_000,
            oracle_verified_records=100,
            total_records=100,
        )
        for spec in LANE_14_SPECS
    }


def test_tier_a_license_firewall_and_planted_nc_rejection() -> None:
    for good in ("CC0", "CC0-1.0", "CC-BY-4.0", "MIT", "Apache-2.0", "ODC-By 1.0", "BSD-3-Clause"):
        dec = check_license_firewall(good)
        assert dec.allowed and dec.tier == "TIER_A", (good, dec)
    for bad in ("CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-ND-4.0", "proprietary", "AGPL-3.0", "academic-only", ""):
        dec = check_license_firewall(bad)
        assert not dec.allowed, (bad, dec)


def test_ds01_13gram_contamination_planted_control(tmp_path: Path) -> None:
    index = ContaminationIndex()
    ds01_sample = "prefix words " + FROZEN_DS_HOLDOUTS["DS-01"][0] + " trailing words"
    hit = index.check_text(ds01_sample)
    assert hit.contaminated and "DS-01" in hit.matched_datasets and hit.matched_ngram_count >= 1
    clean = "a freshly written synthetic derivation explaining symplectic integrators for orbital mechanics without holdout overlap"
    assert not index.check_text(clean).contaminated

    extra = tmp_path / "ds01_custom.jsonl"
    custom_phrase = "custom holdout probe alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu"
    extra.write_text(json.dumps({"prompt": custom_phrase}) + "\n", encoding="utf-8")
    assert index.load_holdout_jsonl("DS-01-LIVE", extra) >= 1
    live_hit = index.check_text("wrapped " + custom_phrase + " end")
    assert live_hit.contaminated and "DS-01-LIVE" in live_hit.matched_datasets


def test_curate_records_filters_nc_and_ds01_contamination() -> None:
    records = [
        {"lane_id": "lane_03_agentic_tool_repair", "license": "MIT", "text": "clean verifiable buildlang trajectory", "tokens": 500, "oracle_verified": True},
        {"lane_id": "lane_03_agentic_tool_repair", "license": "CC-BY-NC-4.0", "text": "non commercial dataset row", "tokens": 500, "oracle_verified": True},
        {"lane_id": "lane_03_agentic_tool_repair", "license": "Apache-2.0", "text": FROZEN_DS_HOLDOUTS["DS-01"][0], "tokens": 500, "oracle_verified": True},
    ]
    summary = curate_records(records)
    assert summary.total_seen == 3
    assert summary.accepted == 1
    assert summary.license_rejected == 1
    assert summary.contamination_rejected == 1
    st = summary.lane_stats["lane_03_agentic_tool_repair"]
    assert st.license_violations == 1 and st.contamination_hits == 1


def test_stage2_blocked_with_no_go_data_gate_on_unverified_or_contaminated_lanes() -> None:
    assert len(LANE_14_SPECS) == 14
    partial = _all_passing_lane_stats()
    partial.pop("lane_14_bio_neuro_chem_med")
    rep = evaluate_readiness(partial)
    assert not rep.ok and rep.verdict == "NO_GO_DATA_GATE"
    assert "lane_14_bio_neuro_chem_med" in rep.blocking_lanes

    blocked_run = run_colab_forge_pipeline(partial, stage="stage2", device="cpu")
    assert not blocked_run["ok"]
    assert blocked_run["verdict"] == "NO_GO_DATA_GATE"
    assert blocked_run["stage2_executed"] is False

    contaminated = _all_passing_lane_stats()
    contaminated["lane_03_agentic_tool_repair"] = LaneStats(
        "lane_03_agentic_tool_repair", 5_000_000_000, 100, 100, contamination_hits=1,
    )
    contam_rep = evaluate_readiness(contaminated)
    assert not contam_rep.ok and contam_rep.verdict == "NO_GO_DATA_GATE"


def test_model_carving_healthy_and_planted_broken_gates() -> None:
    names = ("attn_0", "mlp_0", "attn_1", "mlp_1", "attn_2", "mlp_2")
    params = (100_000, 200_000, 100_000, 200_000, 100_000, 200_000)
    gate = CarvedSublayerGate(names, params, init_logits=[0.4, 0.4, 0.4, 0.4, 0.4, 0.4])
    for _ in range(8):
        gate.carve_step([0.9, 0.8, 0.1, 0.05, 0.7, 0.6], target_sparsity=0.33, lr=0.45)
    health = validate_carving_health(gate)
    assert health.healthy and health.verdict == "HEALTHY"
    assert 0.10 <= health.sparsity_ratio <= 0.85

    dead_gate = CarvedSublayerGate(names, params, init_logits=[-10.0] * 6)
    dead_health = validate_carving_health(dead_gate)
    assert not dead_health.healthy and dead_health.verdict == "COLLAPSED_CARVING_GATE"

    unpruned_gate = CarvedSublayerGate(names, params, init_logits=[5.0] * 6)
    unpruned_health = validate_carving_health(unpruned_gate)
    assert not unpruned_health.healthy and unpruned_health.verdict == "UNPRUNED_CARVING_GATE"

    nan_gate = CarvedSublayerGate(names, params, init_logits=[0.5, float("nan"), 0.5, -0.5, 0.5, 0.5])
    nan_health = validate_carving_health(nan_gate)
    assert not nan_health.healthy and nan_health.verdict == "NON_FINITE_GATE"


def test_loom_vs_mhc_router_and_oracle_head_and_bit_transfer() -> None:
    router = LoomMHCRouter([[2.2, 0.6, 0.1, 0.3], [0.4, 2.0, 0.5, 0.2], [0.2, 0.3, 2.1, 0.4], [0.5, 0.1, 0.4, 2.3]])
    streams = [[1.0, -0.5, 0.25, 0.5], [-0.5, 1.0, 0.5, -0.25], [0.25, 0.5, 1.0, 0.1], [0.1, -0.2, 0.3, 1.0]]
    mhc = router.route(streams, mode="mhc")
    loom = router.route(streams, mode="loom")
    assert mhc["max_row_sum_err"] < 1e-6 and mhc["max_col_sum_err"] < 1e-6
    assert mhc["amplification_ratio"] <= 1.0001
    assert loom["amplification_ratio"] > mhc["amplification_ratio"]

    oracle = BuildLangOracleHead()
    assert oracle.verify_numeric("PHY_KINETIC_ENERGY", {"mass": 4.0, "velocity": 5.0}, 50.0).passed
    assert not oracle.verify_numeric("PHY_KINETIC_ENERGY", {"mass": 4.0, "velocity": 5.0}, 49.0).passed
    assert not oracle.verify_numeric("PHY_KINETIC_ENERGY", {"mass": 4.0, "velocity": 5.0}, float("nan")).passed
    assert oracle.verify_buildlang_source("fn kinetic(m: f64, v: f64) -> f64 { 0.5 * m * v * v }").passed
    assert not oracle.verify_buildlang_source("fn kinetic() { TODO }").passed

    cap = compute_capacity_bit_transfer(2.5, 1.5, 1000, active_params=600_000, total_params=900_000)
    assert math.isclose(cap["bits_transferred"], 1000.0 / math.log(2.0), rel_tol=1e-5)
    assert math.isclose(cap["parameter_reduction_ratio"], 1.0 / 3.0, rel_tol=1e-5)
    assert math.isclose(cap["effective_density_gain"], 1.5, rel_tol=1e-5)

    gate = CarvedSublayerGate(("a0", "m0", "a1", "m1"), (100, 200, 100, 200), (0.8, 0.8, -0.5, -0.5))
    step = JFC3PCarvedModel(gate, router, oracle).evaluate_step(streams, router_mode="mhc")
    assert step["carving_health"]["healthy"] and step["capacity_diagnostics"]["effective_density_gain"] == 2.0


def test_chunked_151k_exact_reverse_kl_parity() -> None:
    rng = random.Random(42)
    q_logits = [rng.uniform(-3.0, 3.0) for _ in range(1024)]
    p_logits = [rng.uniform(-3.0, 3.0) for _ in range(1024)]
    dense = dense_exact_reverse_kl(q_logits, p_logits)
    chunked_odd = chunked_exact_reverse_kl(q_logits, p_logits, chunk_size=37)
    chunked_pow2 = chunked_exact_reverse_kl(q_logits, p_logits, chunk_size=256)
    assert abs(dense - chunked_odd) < 1e-12
    assert abs(dense - chunked_pow2) < 1e-12

    bench = benchmark_151k_reverse_kl(vocab_size=151_936, chunk_size=4096, parity_vocab=1024, device="cpu")
    assert bench["parity_abs_err"] < 1e-12
    assert bench["streaming_151k"]["vocab_size"] == 151_936
    assert bench["streaming_151k"]["kl_nats"] > 0.0


def test_stage2_go_pipeline_and_receipt_tamper_control(tmp_path: Path) -> None:
    res = run_colab_forge_pipeline(_all_passing_lane_stats(), stage="stage2", device="cpu", vocab_size=8192, out_dir=tmp_path)
    assert res["ok"] and res["verdict"] == "GO" and res["stage2_executed"] is True
    receipt_path = tmp_path / "engine_receipt.json"
    summary_path = tmp_path / "forge_run_summary.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    ok, errs = verify_forge_receipt(receipt, check_files=True)
    assert ok and errs == []

    # Planted 1-byte artifact tamper must fail closed.
    summary_path.write_text(summary_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    tampered_ok, tampered_errs = verify_forge_receipt(receipt, check_files=True)
    assert not tampered_ok and any("drift" in e for e in tampered_errs)

    # Planted MATCH verdict with exit_code=1 must fail closed.
    bad_rec = build_forge_receipt(
        task_id="bad", artifact_paths=[summary_path], oracle_exit_code=1,
        oracle_stdout="[FAIL] planted failure\n", oracle_command=["pytest"], root=tmp_path,
    )
    assert bad_rec["verdict"] == "DRIFT"
    bad_rec["verdict"] = "MATCH"
    bad_ok, bad_errs = verify_forge_receipt(bad_rec, check_files=False)
    assert not bad_ok and any("fail-closed" in e for e in bad_errs)


def test_jfc3p_forge_maintainability_and_zero_em_dash_hygiene() -> None:
    targets = sorted(FORGE_DIR.glob("*.py")) + [Path(__file__).resolve()]
    assert len(targets) >= 5
    for path in targets:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 300, f"{path.name} exceeds 300 lines: {len(lines)}"
        assert "\u2014" not in text and "\u2013" not in text, f"em/en dash found in {path.name}"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{path.name}:{node.name} exceeds 50 lines ({span})"
