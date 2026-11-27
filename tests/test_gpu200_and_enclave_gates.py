# SPDX-License-Identifier: MIT
"""Unit tests for harness/gpu_shader_200_gate and harness/enclave_quote_gate."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

from harness.enclave_quote_gate import (
    HONEST_SCOPE_LIMIT as ENCLAVE_SCOPE_LIMIT,
)
from harness.enclave_quote_gate import (
    REQUIRED_ENCLAVE_ISAS,
    EnclaveQuoteSpec,
    EnclaveTargetRun,
    validate_binary_magic,
    verify_enclave_quote,
    verify_enclave_receipt_file,
)
from harness.gpu_shader_200_gate import (
    HONEST_SCOPE_LIMIT as GPU200_SCOPE_LIMIT,
)
from harness.gpu_shader_200_gate import (
    REQUIRED_GPU_TARGETS,
    verify_gpu_200_pack,
    verify_gpu_200_pack_files,
)

H64 = "a" * 64
H32 = "b" * 32


def _sample_gpu_manifest(n_kernels: int = 2) -> dict[str, Any]:
    val_map = {
        "wgsl": "naga-30.0.1-PASS",
        "hlsl": "dxc-cs_6_0-PASS",
        "msl": "metal-3.1-PASS",
        "spirv": "spirv-val-PASS",
        "glsl": "glslangValidator+spirv-val-PASS",
    }
    shaders: list[dict[str, Any]] = []
    for i in range(n_kernels):
        for tgt in sorted(REQUIRED_GPU_TARGETS):
            shaders.append({
                "batch": "batch1",
                "kernel": f"kern_{i}",
                "target": tgt,
                "shader_bytes": 1000,
                "shader_sha256": H64,
                "cert_sha256": H64,
                "rewrites": 5,
                "verify_cert": "PASS",
                "external_validator": val_map[tgt],
            })
    return {
        "license": "MIT",
        "unique_kernels": n_kernels,
        "gpu_targets": 5,
        "total_certified_shaders": len(shaders),
        "per_target_counts": {t: n_kernels for t in sorted(REQUIRED_GPU_TARGETS)},
        "total_shader_bytes": len(shaders) * 1000,
        "total_superopt_rewrites": len(shaders) * 5,
        "shaders": shaders,
    }


def _sample_enclave_spec(
    *,
    nonce_seq: int = 42,
    granted_caps: int = 5,
    attacks: int = 4,
    omit_isa: str | None = None,
) -> EnclaveQuoteSpec:
    runs = tuple(
        EnclaveTargetRun(isa, 1, 1, 28, nonce_seq, granted_caps, H64, H64, attacks, 4096, H64)
        for isa in sorted(REQUIRED_ENCLAVE_ISAS)
        if isa != omit_isa
    )
    return EnclaveQuoteSpec(H64, H64, H64, H32, H64, 41, 28, runs)


def test_gpu200_clean_pass_and_deterministic_attestation() -> None:
    mat = _sample_gpu_manifest(2)
    r1 = verify_gpu_200_pack(mat, min_shaders=10, min_kernels=2, min_rewrites=50)
    r2 = verify_gpu_200_pack(mat, min_shaders=10, min_kernels=2, min_rewrites=50)
    assert r1.passed and r1.total_shaders == 10 and r1.complete_5target_kernels == 2
    assert r1.total_superopt_rewrites == 50 and len(r1.gpu_shader_200_attestation_sha256) == 64
    assert r1.gpu_shader_200_attestation_sha256 == r2.gpu_shader_200_attestation_sha256


def test_gpu200_rejects_shortfall_forged_sha_and_failing_validator() -> None:
    mat = _sample_gpu_manifest(2)
    assert not verify_gpu_200_pack(mat, min_shaders=200, min_kernels=40, min_rewrites=50).passed
    bad_hash = {("kern_0", "wgsl"): (1000, "0" * 64)}
    assert not verify_gpu_200_pack(mat, min_shaders=10, min_kernels=2, min_rewrites=50, actual_shader_hashes=bad_hash).passed
    m2 = copy.deepcopy(mat)
    m2["shaders"][0]["external_validator"] = "dxc-FAIL"
    assert not verify_gpu_200_pack(m2, min_shaders=10, min_kernels=2, min_rewrites=50).passed
    m3 = copy.deepcopy(mat)
    m3["license"] = "AGPL-3.0-only"
    assert not verify_gpu_200_pack(m3, min_shaders=10, min_kernels=2, min_rewrites=50).passed


@pytest.mark.parametrize("bad_err", [math.nan, math.inf, -math.inf, True, False, -0.1, "NaN"])
def test_gpu200_rejects_non_finite_and_bool_parity(bad_err: Any) -> None:
    mat = _sample_gpu_manifest(2)
    assert not verify_gpu_200_pack(mat, min_shaders=10, min_kernels=2, min_rewrites=50, observed_parity_err=bad_err).passed
    assert not verify_gpu_200_pack(mat, min_shaders=10, min_kernels=2, min_rewrites=50, max_parity_err=bad_err).passed


@pytest.mark.parametrize("bad_cnt", [True, False, 0, -1, math.nan])
def test_gpu200_rejects_invalid_min_shaders(bad_cnt: Any) -> None:
    assert not verify_gpu_200_pack(_sample_gpu_manifest(2), min_shaders=bad_cnt, min_kernels=2, min_rewrites=0).passed


def test_gpu200_file_roundtrip_and_missing(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_sample_gpu_manifest(2)), encoding="utf-8")
    assert verify_gpu_200_pack_files(p, min_shaders=10, min_kernels=2, min_rewrites=50).passed
    assert not verify_gpu_200_pack_files(tmp_path / "missing.json").passed


def test_enclave_clean_pass_and_deterministic_attestation() -> None:
    spec = _sample_enclave_spec()
    r1 = verify_enclave_quote(spec)
    r2 = verify_enclave_quote(spec)
    assert r1.passed and r1.isa_count == 5 and r1.zero_egress_verified
    assert r1.min_nonce_seq == 42 and r1.min_attacks_caught == 4
    assert len(r1.enclave_quote_attestation_sha256) == 64
    assert r1.enclave_quote_attestation_sha256 == r2.enclave_quote_attestation_sha256


def test_enclave_rejects_stale_nonce_egress_violation_and_missing_isa() -> None:
    stale = _sample_enclave_spec(nonce_seq=41)
    assert not verify_enclave_quote(stale).passed
    egress = _sample_enclave_spec(granted_caps=7)
    rep_e = verify_enclave_quote(egress)
    assert not rep_e.passed and not rep_e.zero_egress_verified
    missing = _sample_enclave_spec(omit_isa="rv64-elf")
    assert not verify_enclave_quote(missing).passed
    low_att = _sample_enclave_spec(attacks=3)
    assert not verify_enclave_quote(low_att).passed


def test_enclave_rejects_zero_digest_and_binary_hash_tamper() -> None:
    bad_spec = EnclaveQuoteSpec("0" * 64, H64, H64, H32, H64, 41, 28, _sample_enclave_spec().targets)
    assert not verify_enclave_quote(bad_spec).passed
    bad_hashes = {isa: (4096, "c" * 64) for isa in REQUIRED_ENCLAVE_ISAS}
    assert not verify_enclave_quote(_sample_enclave_spec(), actual_binary_hashes=bad_hashes).passed


@pytest.mark.parametrize("bad_ms", [math.nan, math.inf, -math.inf, True, False, 0.0, -5.0])
def test_enclave_rejects_invalid_max_emit_ms(bad_ms: Any) -> None:
    assert not verify_enclave_quote(_sample_enclave_spec(), max_emit_ms=bad_ms).passed


@pytest.mark.parametrize(
    ("isa", "hdr", "ok"),
    [("x64-pe", b"MZ\x90\x00", True), ("rv64-elf", b"\x7fELF", True), ("wasm", b"\x00asm", True), ("wasm", b"MZ\x90\x00", False)],
)
def test_enclave_magic_validation(isa: str, hdr: bytes, ok: bool) -> None:
    assert validate_binary_magic(isa, hdr) is ok


def test_enclave_receipt_roundtrip_and_missing(tmp_path: Path) -> None:
    rec = {
        "verdict": "MATCH",
        "oracle": {"exit_code": 0},
        "subject": {
            "artifacts": [
                {"rel_path": "out/e.aarch64.elf", "bytes": 100, "sha256": f"sha256:{H64}"},
                {"rel_path": "out/e.rv64.elf", "bytes": 100, "sha256": f"sha256:{H64}"},
                {"rel_path": "out/e.x64.elf", "bytes": 100, "sha256": f"sha256:{H64}"},
                {"rel_path": "out/e.exe", "bytes": 100, "sha256": f"sha256:{H64}"},
                {"rel_path": "out/e.wasm", "bytes": 100, "sha256": f"sha256:{H64}"},
            ]
        },
    }
    rp = tmp_path / "enclave.json"
    rp.write_text(json.dumps(rec), encoding="utf-8")
    ok = verify_enclave_receipt_file(rp, mr_enclave_hex=H64, enclave_root_hex=H64, quote_digest_hex=H64, aead_tag_hex=H32, ed_pt_hex=H64)
    assert ok.passed and ok.isa_count == 5
    assert not verify_enclave_receipt_file(tmp_path / "no.json", mr_enclave_hex=H64, enclave_root_hex=H64, quote_digest_hex=H64, aead_tag_hex=H32, ed_pt_hex=H64).passed


@pytest.mark.parametrize("bad_caps", [True, False, -1, 2, 3, 7, 8, "5"])
def test_enclave_rejects_invalid_and_egress_caps(bad_caps: Any) -> None:
    spec = _sample_enclave_spec(granted_caps=bad_caps)
    assert not verify_enclave_quote(spec).passed


def test_explicit_honest_scope_limits_present() -> None:
    assert "Pure-Python stdlib" in GPU200_SCOPE_LIMIT
    assert "Pure-Python stdlib" in ENCLAVE_SCOPE_LIMIT
