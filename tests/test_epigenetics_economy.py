# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Unit and planted-control tests for harness.epigenetics_economy (J13, J14, J12)."""
from __future__ import annotations

import math

import pytest

from harness.epigenetics_economy import (
    CheckedClaimMarketplace,
    EpigeneticError,
    LatentChecksumError,
    LemmaReceipt,
    analyze_lora_factors,
    analyze_matrix_spectrum,
    build_orthonormal_basis,
    classify_spectral_regime,
    decode_latent_packet,
    encode_latent_packet,
    run_checked_claim_arena,
    seal_epigenetic_receipt,
    verify_epigenetic_receipt,
)


def _honest_core_8x8() -> list[list[float]]:
    out: list[list[float]] = []
    for r in range(8):
        row: list[float] = []
        for c in range(8):
            val = 0.55 * math.sin(float(r * 11 + c * 17 + r * c * 5 + 3) * 0.57) + 0.45 * math.cos(
                float(r * 19 - c * 7 + r * c * 3 + 5) * 0.31
            )
            if r == c:
                val += 0.90
            row.append(val)
        out.append(row)
    return out


def _shortcut_core_8x8() -> list[list[float]]:
    out: list[list[float]] = []
    for r in range(8):
        row: list[float] = []
        for c in range(8):
            u_r = 1.0 + 0.25 * (float(r) - 3.5)
            v_c = 1.0 - 0.15 * (float(c) - 3.5)
            row.append(0.95 * u_r * v_c + 0.04 * math.sin(float((r * 8 + c) * 17 + 1) * 0.63))
        out.append(row)
    return out


def test_j13_epigenetics_separates_honest_vs_shortcut_and_seals_receipt() -> None:
    sig_honest = analyze_matrix_spectrum(_honest_core_8x8())
    sig_shortcut = analyze_matrix_spectrum(_shortcut_core_8x8())

    assert sig_honest.effective_rank > 5.0
    assert sig_shortcut.effective_rank < 1.05
    assert sig_honest.effective_rank / sig_shortcut.effective_rank > 5.0
    assert sig_shortcut.top1_energy_ratio > 0.99
    assert classify_spectral_regime(sig_honest) == "MULTI_FEATURE_HONEST"
    assert classify_spectral_regime(sig_shortcut) == "SHORTCUT_COLLAPSED"

    receipt = seal_epigenetic_receipt("adapter-honest-01", sig_honest)
    assert receipt["inference_calls"] == 0
    assert verify_epigenetic_receipt(receipt) is True

    # Planted tamper control: mutate regime without re-sealing -> rejected fail-closed
    forged = dict(receipt)
    forged["regime"] = "SHORTCUT_COLLAPSED"
    assert verify_epigenetic_receipt(forged) is False


def test_j13_planted_rank1_isotropic_and_zero_controls() -> None:
    # Exact rank-1 outer product -> eff_rank == 1.0, top1 == 1.0
    rank1 = [[(0.5 + 0.3 * r) * (1.2 - 0.1 * c) for c in range(8)] for r in range(8)]
    s_r1 = analyze_matrix_spectrum(rank1)
    assert abs(s_r1.effective_rank - 1.0) < 1.0e-12
    assert abs(s_r1.top1_energy_ratio - 1.0) < 1.0e-12

    # Exact isotropic identity I_8 -> eff_rank == 8.0, top1 == 0.125
    eye8 = [[1.0 if r == c else 0.0 for c in range(8)] for r in range(8)]
    s_iso = analyze_matrix_spectrum(eye8)
    assert abs(s_iso.effective_rank - 8.0) < 1.0e-12
    assert abs(s_iso.top1_energy_ratio - 0.125) < 1.0e-12

    # Planted zero-energy matrix -> fail-closed EpigeneticError
    zeros = [[0.0] * 8 for _ in range(8)]
    with pytest.raises(EpigeneticError, match="ZERO_ENERGY_MATRIX"):
        analyze_matrix_spectrum(zeros)

    # Planted NaN weight -> fail-closed EpigeneticError
    bad = [[1.0, float("nan")], [0.0, 1.0]]
    with pytest.raises(EpigeneticError, match="NON_FINITE_WEIGHT"):
        analyze_matrix_spectrum(bad)


def test_j13_lora_factor_contraction_matches_explicit_product() -> None:
    # B (16 x 4) and A (4 x 12) -> thin-QR contraction must match explicit B @ A exactly
    b_mat = [[math.sin((r * 7 + c * 11 + 1) * 0.37) for c in range(4)] for r in range(16)]
    a_mat = [[math.cos((r * 13 + c * 5 + 2) * 0.29) for c in range(12)] for r in range(4)]
    alpha = 0.5
    dense = [
        [alpha * sum(b_mat[r][k] * a_mat[k][c] for k in range(4)) for c in range(12)]
        for r in range(16)
    ]

    sig_fact = analyze_lora_factors(b_mat, a_mat, alpha=alpha)
    sig_dense = analyze_matrix_spectrum(dense)
    assert sig_fact.rows == 16 and sig_fact.cols == 12
    assert abs(sig_fact.effective_rank - sig_dense.effective_rank) < 1.0e-11
    assert abs(sig_fact.top1_energy_ratio - sig_dense.top1_energy_ratio) < 1.0e-11
    assert abs(sig_fact.frobenius_norm - sig_dense.frobenius_norm) < 1.0e-11


def test_j14_checked_claim_arena_and_fail_closed_tamper_rejection() -> None:
    res = run_checked_claim_arena()
    assert res["ok"] is True
    assert res["tasks"] == 60
    assert res["abs_gain_over_isolated_mean_pp"] >= 20.0
    assert res["abs_gain_over_isolated_best_pp"] >= 20.0
    assert res["poison_rejected"] == res["poison_planted"] == 30
    assert res["tampered_rejected"] == res["tampered_planted"] == 10
    assert res["gossip_poison_consumed"] > 0
    assert res["gossip_mean_accuracy"] < res["checked_swarm_mean_accuracy"] - 0.25
    assert res["adversary_credits"] < 0.0
    assert all(v > 0.0 for v in res["honest_credits"].values())

    # Direct marketplace fail-closed check on unsigned / unverified receipt
    mkt = CheckedClaimMarketplace()
    fake_rec = LemmaReceipt(
        task_id="MATH-01",
        step_idx=0,
        domain="math",
        author="agent_byzantine",
        value=99999,
        oracle_verified=False,
        receipt_sha256="0" * 64,
    )
    assert mkt.verify_receipt_fail_closed(fake_rec) is False


def test_j12_latent_handoff_roundtrip_and_corrupt_bit_rejection() -> None:
    q = build_orthonormal_basis(36)
    state = [
        3.2 * math.sin(float(j * 13 + 5) * 0.4137) + 0.3 * math.cos(float(j * 7 + 11) * 0.7319)
        for j in range(36)
    ]
    pkt = encode_latent_packet(state, q)
    assert len(pkt) == 48
    # Bit-exact tag match with native BuildLang SIG-067 kernel on scene 0
    assert pkt[40:].hex() == "671eb7a3effb62e6"

    rec = decode_latent_packet(pkt, q)
    mse = sum((a - b) ** 2 for a, b in zip(rec, state)) / 36.0
    assert mse < 0.0005

    # Planted control: 1-bit flip in byte 12 -> fail-closed LatentChecksumError
    corrupted = bytearray(pkt)
    corrupted[12] ^= 0x01
    with pytest.raises(LatentChecksumError, match="LATENT_SHA256_MISMATCH"):
        decode_latent_packet(bytes(corrupted), q)
