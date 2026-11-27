# SPDX-License-Identifier: MIT
"""Unit and adversarial tamper tests for harness.gpu_cert_bridge."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from harness import gpu_cert_bridge as gcb


def _make_superopt_cert(target: str, *, before: int = 4, after: int = 2, ulps: int = 1) -> dict:
    return {
        "schema": gcb.SUPEROPT_CERT_SCHEMA,
        "target": target,
        "mir_before_sha256": "a" * 64,
        "mir_after_sha256": "b" * 64,
        "functions_visited": 1,
        "rewrites_applied": 1,
        "total_cost_before": before,
        "total_cost_after": after,
        "verified": True,
        "steps": [
            {
                "function": "demo_kernel",
                "rule": "R18_FMA_CONTRACT",
                "cost_before": before,
                "cost_after": after,
                "error_witness": {"kind": "bounded_ulp", "max_ulps": ulps},
            }
        ],
        "cert_sha256": "c" * 64,
    }


def _make_gpu_cert(target: str, shader_bytes: bytes, *, superopt: dict | None = None) -> dict:
    return {
        "schema": gcb.GPU_CERT_SCHEMA,
        "target": target,
        "subgroup_intrinsic": "subgroupAdd",
        "superopt_cert": superopt if superopt is not None else _make_superopt_cert(target),
        "polyhedral_schedules": [{"function": "demo_kernel", "verified": True}],
        "subgroup_plan": {
            "mode": {"kind": "strict_bit_exact", "scale_shift": 16, "fixed_block_size": 256},
            "reduction_op": "sum",
            "intrinsic": "subgroupAdd",
            "uniformity_verified": True,
            "widths_verified": [16, 32, 64],
            "width_invariance_sha256": "d" * 64,
            "max_cross_width_abs_diff": 0.0,
        },
        "shader_sha256": gcb.sha256_hex(shader_bytes),
        "verified": True,
        "cert_sha256": "e" * 64,
    }


def _write_kernel_bundle(root: Path, kernel: str) -> dict[str, tuple[Path, Path]]:
    paths: dict[str, tuple[Path, Path]] = {}
    for target in gcb.REQUIRED_GPU_TARGETS:
        shader_bytes = f"// {kernel} target={target}\n".encode()
        shader_path = root / f"{kernel}{gcb.TARGET_SHADER_EXT[target]}"
        cert_path = root / f"{kernel}.{target}.gpu-cert.json"
        shader_path.write_bytes(shader_bytes)
        cert_path.write_text(json.dumps(_make_gpu_cert(target, shader_bytes)), encoding="utf-8")
        paths[target] = (cert_path, shader_path)
    return paths


def test_matrix_gate_passes_complete_two_kernel_five_target_bundle(tmp_path: Path) -> None:
    _write_kernel_bundle(tmp_path, "kernel_alpha")
    _write_kernel_bundle(tmp_path, "kernel_beta")
    rep = gcb.verify_gpu_cert_matrix(tmp_path, expected_kernels=("kernel_alpha", "kernel_beta"))
    assert rep.passed is True
    assert rep.kernels_checked == 2 and rep.shaders_verified == 10
    assert rep.reasons == () and len(rep.attestation_sha256) == 64
    assert rep.to_dict()["passed"] is True


@pytest.mark.parametrize("dropped", gcb.REQUIRED_GPU_TARGETS)
def test_matrix_gate_missing_target_fails_closed(tmp_path: Path, dropped: str) -> None:
    paths = _write_kernel_bundle(tmp_path, "demo_kernel")
    paths[dropped][0].unlink()
    rep = gcb.verify_gpu_cert_matrix(tmp_path)
    assert rep.passed is False
    assert rep.entries[0].missing_targets == (dropped,)
    assert f"MISSING_TARGET:demo_kernel:{dropped}" in rep.reasons


@pytest.mark.parametrize("tampered", gcb.REQUIRED_GPU_TARGETS)
def test_matrix_gate_1bit_shader_tamper_fails_closed(tmp_path: Path, tampered: str) -> None:
    paths = _write_kernel_bundle(tmp_path, "demo_kernel")
    shader_path = paths[tampered][1]
    raw = bytearray(shader_path.read_bytes())
    raw[0] ^= 1
    shader_path.write_bytes(bytes(raw))
    rep = gcb.verify_gpu_cert_matrix(tmp_path)
    assert rep.passed is False
    assert f"demo_kernel:{tampered}:SHADER_SHA256_MISMATCH" in rep.reasons


def test_shader_cert_rejects_bad_schema_target_unverified_and_empty() -> None:
    cert = _make_gpu_cert("wgsl", b"fn main() {}")
    cert["schema"] = "wrong/v0"
    cert["verified"] = False
    cert["cert_sha256"] = "short"
    rep = gcb.verify_shader_cert(cert, b"", expected_target="hlsl")
    assert rep.passed is False
    assert {"INVALID_SCHEMA", "TARGET_MISMATCH:wgsl!=hlsl", "CERT_NOT_VERIFIED",
            "MALFORMED_CERT_SHA256", "EMPTY_SHADER_BYTES"} <= set(rep.reasons)


def test_shader_cert_rejects_subgroup_and_polyhedral_failures() -> None:
    raw = b"shader-body"
    cert = _make_gpu_cert("glsl", raw)
    cert["subgroup_plan"]["uniformity_verified"] = False
    cert["subgroup_plan"]["max_cross_width_abs_diff"] = 0.25
    cert["polyhedral_schedules"] = [{"function": "f", "verified": False}]
    rep = gcb.verify_shader_cert(cert, raw, expected_target="glsl")
    assert rep.passed is False
    assert "SUBGROUP_UNIFORMITY_FAILED" in rep.reasons
    assert "SUBGROUP_BIT_EXACT_DRIFT" in rep.reasons
    assert "POLYHEDRAL_SCHEDULE_UNVERIFIED:0" in rep.reasons


def test_shader_cert_files_missing_and_invalid_json(tmp_path: Path) -> None:
    missing = gcb.verify_shader_cert_files(tmp_path / "no.json", tmp_path / "no.wgsl")
    assert missing.passed is False and "MISSING_CERT_FILE" in missing.reasons
    bad_json = tmp_path / "bad.wgsl.gpu-cert.json"
    shader = tmp_path / "bad.wgsl"
    bad_json.write_text("{not-json", encoding="utf-8")
    shader.write_bytes(b"ok")
    rep = gcb.verify_shader_cert_files(bad_json, shader)
    assert rep.passed is False and "INVALID_CERT_JSON" in rep.reasons


@pytest.mark.parametrize("target", gcb.REQUIRED_GPU_TARGETS)
def test_superopt_monotone_cost_passes_and_computes_delta(target: str) -> None:
    rep = gcb.verify_superopt_cert(_make_superopt_cert(target, before=10, after=6), expected_target=target)
    assert rep.passed is True and rep.cost_delta == 4 and rep.to_dict()["cost_delta"] == 4


@pytest.mark.parametrize("target", gcb.REQUIRED_GPU_TARGETS)
def test_superopt_total_and_step_cost_regression_fails_closed(target: str) -> None:
    rep = gcb.verify_superopt_cert(_make_superopt_cert(target, before=4, after=7))
    assert rep.passed is False
    assert "TOTAL_COST_REGRESSION:4->7" in rep.reasons
    assert "STEP_COST_REGRESSION:0:4->7" in rep.reasons


def test_superopt_rewrite_mismatch_sum_mismatch_and_ulp_bound() -> None:
    so = _make_superopt_cert("spirv", before=4, after=2, ulps=4)
    so["rewrites_applied"] = 2
    so["total_cost_before"] = 9
    rep = gcb.verify_superopt_cert(so, max_allowed_ulps=1)
    assert rep.passed is False
    assert "REWRITE_COUNT_MISMATCH:1!=2" in rep.reasons
    assert "STEP_ULP_EXCEEDS_BOUND:0:4" in rep.reasons
    assert any(r.startswith("STEP_COST_SUM_MISMATCH:") for r in rep.reasons)


def test_superopt_rejects_bool_cost_unverified_and_bad_digests() -> None:
    so = _make_superopt_cert("wgsl")
    so["verified"] = False
    so["total_cost_before"] = True
    so["mir_before_sha256"] = "xyz"
    rep = gcb.verify_superopt_cert(so, expected_target="glsl")
    assert rep.passed is False
    assert {"SUPEROPT_NOT_VERIFIED", "INVALID_TOTAL_COST", "MALFORMED_MIR_BEFORE_SHA256",
            "SUPEROPT_TARGET_MISMATCH:wgsl!=glsl"} <= set(rep.reasons)


def test_matrix_gate_catches_cost_regression_and_missing_superopt(tmp_path: Path) -> None:
    paths = _write_kernel_bundle(tmp_path, "k_reg")
    cert_path, shader_path = paths["spirv"]
    bad_cert = _make_gpu_cert("spirv", shader_path.read_bytes(), superopt=_make_superopt_cert("spirv", before=3, after=5))
    cert_path.write_text(json.dumps(bad_cert), encoding="utf-8")
    cert_wgsl, _ = paths["wgsl"]
    obj = json.loads(cert_wgsl.read_text(encoding="utf-8"))
    del obj["superopt_cert"]
    cert_wgsl.write_text(json.dumps(obj), encoding="utf-8")
    rep = gcb.verify_gpu_cert_matrix(tmp_path)
    assert rep.passed is False
    assert "k_reg:spirv:TOTAL_COST_REGRESSION:3->5" in rep.reasons
    assert "MISSING_SUPEROPT_CERT:k_reg:wgsl" in rep.reasons


def test_matrix_gate_empty_missing_dir_and_missing_expected_kernel(tmp_path: Path) -> None:
    assert gcb.verify_gpu_cert_matrix(tmp_path / "nope").passed is False
    assert "EMPTY_MATRIX" in gcb.verify_gpu_cert_matrix(tmp_path).reasons
    _write_kernel_bundle(tmp_path, "present_kernel")
    rep = gcb.verify_gpu_cert_matrix(tmp_path, expected_kernels=("present_kernel", "absent_kernel"))
    assert rep.passed is False
    assert any(r.startswith("MISSING_TARGET:absent_kernel:") for r in rep.reasons)


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "gpu_cert_bridge").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(gcb.HONEST_SCOPE_LIMITS) == {"shader_cert", "superopt_chain", "matrix_gate"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
