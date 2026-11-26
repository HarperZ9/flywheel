"""Unit tests and planted-failure controls for Wave 21B-4 FRESCO, MoLT, LoopCD & Plato-Key 128x (CPU-only)."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import random

import pytest

from plexus.jfc3p_forge import (
    FRESCOOrthogonalProjector,
    MoLTCrossLoopKVCache,
    PlatoKeyLatentCodec,
    fused_single_pass_loopcd,
    run_ablation_a5_fresco_molt,
    run_wave15_colab_ablations,
    verify_forge_receipt,
)

FORGE_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus" / "jfc3p_forge"


def test_fresco_orthogonal_projection_and_planted_drift_control() -> None:
    rng = random.Random(101)
    x_bar = [[rng.gauss(0.0, 1.0) for _ in range(8)] for _ in range(4)]
    delta = [[rng.gauss(0.0, 0.6) for _ in range(8)] for _ in range(5)]
    proj = FRESCOOrthogonalProjector()

    # Planted unprojected LoRA update MUST fail forward-equivalence on prefix tokens.
    raw = proj.verify_forward_equivalence(delta, x_bar)
    assert raw["forward_equivalent"] is False
    assert raw["prefix_residual_norm"] > 0.1

    # Projected Delta* = Delta (I - P_{X_bar}) MUST satisfy ||Delta* X_bar||_F < 1e-13.
    delta_star = proj.project(delta, x_bar)
    chk = proj.verify_forward_equivalence(delta_star, x_bar)
    assert chk["forward_equivalent"] is True
    assert chk["prefix_residual_norm"] < 1e-13
    assert chk["delta_frob_norm"] > 0.1


def test_molt_cross_loop_kv_reuse_and_planted_kv_corruption_control() -> None:
    cache = MoLTCrossLoopKVCache(sim_threshold=0.92)
    k0 = [1.0, 0.5, -0.25, 0.75]
    v0 = [0.2, 0.4, 0.6, 0.8]
    cache.put(0, 0, k0, v0)

    # Close query hits cached KV without recomputation.
    val, hit = cache.fetch_or_compute(0, 0, [1.01, 0.49, -0.24, 0.76], [9.0, 9.0, 9.0, 9.0])
    assert hit is True and val == v0

    # Dissimilar query triggers cache miss and refresh.
    val_miss, hit_miss = cache.fetch_or_compute(0, 0, [-1.0, -0.5, 0.25, -0.75], [0.1, 0.1, 0.1, 0.1])
    assert hit_miss is False and val_miss == [0.1, 0.1, 0.1, 0.1]

    # Planted silent KV memory tamper MUST be caught fail-closed by digest verification.
    cache.inject_tamper(0, 0, [999.0, 999.0, 999.0, 999.0])
    val_rec, hit_rec = cache.fetch_or_compute(0, 0, [-1.0, -0.5, 0.25, -0.75], [0.3, 0.3, 0.3, 0.3])
    assert hit_rec is False and val_rec == [0.3, 0.3, 0.3, 0.3]
    assert cache.corruptions_caught == 1


def test_fused_single_pass_loopcd_zero_drift_and_omega_guardrail() -> None:
    res = fused_single_pass_loopcd([3.0, -1.2, 0.5, 2.2], [2.4, -0.8, 0.1, 1.6], omega=0.5)
    assert res["zero_drift"] is True
    assert res["max_abs_drift_vs_two_pass"] < 1e-14

    # Planted guardrail violations (omega > 0.5 or negative) MUST raise ValueError.
    for bad_omega in (-0.1, 0.51, 1.2, float("nan")):
        with pytest.raises(ValueError, match="guardrail"):
            fused_single_pass_loopcd([1.0, 2.0], [0.5, 1.5], omega=bad_omega)


def test_plato_key_128x_codec_and_planted_non_orthogonal_shear_rejection() -> None:
    codec = PlatoKeyLatentCodec(target_compression_x=128)
    # Planted non-orthogonal shear matrix MUST be rejected by orthogonality gate.
    bad_rot = [[2.0, 1.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    assert codec.bind_orthogonal_bridge(bad_rot)["verdict"] == "NON_ORTHOGONAL_BRIDGE_REJECTED"

    # Valid Givens rotation binds cleanly and compresses 128 tokens -> 1 slot (128x).
    c, s = math.cos(0.45), math.sin(0.45)
    rot = [[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    assert codec.bind_orthogonal_bridge(rot, scale=1.5)["ok"] is True
    seq = [[float(i % 5), float((i + 1) % 3), 0.5, -0.25] for i in range(128)]
    slots = codec.compress_sequence(seq)
    ref = [[1.5 * (rot[r][0] * sl[0] + rot[r][1] * sl[1] + rot[r][2] * sl[2] + rot[r][3] * sl[3]) for r in range(4)] for sl in slots]
    ok_res = codec.handoff_and_verify(seq, ref)
    assert ok_res["ok"] is True and ok_res["compression_x"] == 128.0 and ok_res["rel_recon_err"] < 1e-12

    # Planted corrupted target slots MUST fail the reconstruction residual gate.
    bad_res = codec.handoff_and_verify(seq, [[99.0, 99.0, 99.0, 99.0]])
    assert bad_res["ok"] is False and bad_res["verdict"] == "RECON_RESIDUAL_EXCEEDED"


def test_ablation_a5_wired_into_colab_runner_and_receipt_tamper_control(tmp_path: Path) -> None:
    a5 = run_ablation_a5_fresco_molt()
    assert a5["ok"] is True
    assert a5["fresco"]["projected_norm"] < 1e-13
    assert a5["molt_kv"]["reuse_hit_ratio"] >= 0.85 and a5["molt_kv"]["corruptions_caught"] == 1
    assert a5["loopcd"]["zero_drift"] is True
    assert a5["plato_key_128x"]["compression_x"] == 128.0

    run = run_wave15_colab_ablations(ablation="A5", gpu_name="H100", out_dir=tmp_path)
    assert run["ok"] is True and "A5" in run["results"]
    rec = json.loads((tmp_path / "engine_receipt.json").read_text(encoding="utf-8"))
    assert verify_forge_receipt(rec, check_files=True) == (True, [])
    summary = tmp_path / "wave15_ablation_summary.json"
    summary.write_text(summary.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not verify_forge_receipt(rec, check_files=True)[0]


def test_wave21b_files_hygiene_and_zero_em_dashes() -> None:
    targets = [FORGE_DIR / "fresco_molt_bridge.py", FORGE_DIR / "wave15_colab_ablation.py", Path(__file__).resolve()]
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
