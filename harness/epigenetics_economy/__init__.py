# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Model Epigenetics (J13), Checked-Claim Economy (J14), and Latent Handoff (J12).

Zero-dependency Python stdlib module for Flywheel:
  - `epigenetics`: zero-inference weight-spectrum forensics (Roy-Vetterli
    effective rank exp(H_spec), top-1 singular energy, Frobenius norm,
    and canonical SHA-256 spectral receipts).
  - `checked_economy`: oracle-gated SHA-256 sealed lemma marketplace with
    ECO-001 honest-vs-faking payoffs and fail-closed poison/tamper rejection.
  - `latent_handoff`: 48-byte orthogonal int8 + f32 + FIPS 180-4 SHA-256
    latent spatial handoff codec with fail-closed integrity verification.
"""
from __future__ import annotations

from harness.epigenetics_economy.arena import (
    build_60_task_benchmark,
    run_checked_claim_arena,
)
from harness.epigenetics_economy.checked_economy import (
    CheckedClaimMarketplace,
    LemmaReceipt,
    LemmaSpec,
    MultiStepTask,
    SpecialistAgent,
    canonical_receipt_hash,
    oracle_eval_final,
    oracle_eval_lemma,
)
from harness.epigenetics_economy.epigenetics import (
    EpigeneticError,
    SpectralSignature,
    analyze_lora_factors,
    analyze_matrix_spectrum,
    classify_spectral_regime,
    seal_epigenetic_receipt,
    verify_epigenetic_receipt,
)
from harness.epigenetics_economy.latent_handoff import (
    LatentChecksumError,
    build_orthonormal_basis,
    decode_latent_packet,
    encode_latent_packet,
)

__all__ = [
    "CheckedClaimMarketplace",
    "EpigeneticError",
    "LatentChecksumError",
    "LemmaReceipt",
    "LemmaSpec",
    "MultiStepTask",
    "SpecialistAgent",
    "SpectralSignature",
    "analyze_lora_factors",
    "analyze_matrix_spectrum",
    "build_60_task_benchmark",
    "build_orthonormal_basis",
    "canonical_receipt_hash",
    "classify_spectral_regime",
    "decode_latent_packet",
    "encode_latent_packet",
    "oracle_eval_final",
    "oracle_eval_lemma",
    "run_checked_claim_arena",
    "seal_epigenetic_receipt",
    "verify_epigenetic_receipt",
]
