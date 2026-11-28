# SPDX-License-Identifier: MIT
"""Fixture builders for threshold_storage_attest and gpu_shader_520_gate tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HEX64_A = "a" * 64
HEX64_B = "b" * 64
SHA_PREF_A = "sha256:" + HEX64_A
SHA_PREF_B = "sha256:" + HEX64_B

ISA_SPECS = (
    (".exe", b"MZ\x90\x00" + b"\x00" * 60),
    (".x64.elf", b"\x7fELF\x02\x01" + b"\x00" * 58),
    (".rv64.elf", b"\x7fELF\x02\x01" + b"\x01" * 58),
    (".aarch64.elf", b"\x7fELF\x02\x01" + b"\x02" * 58),
    (".wasm", b"\x00asm\x01\x00\x00\x00" + b"\x00" * 56),
)


def _make_slice_artifacts(
    root: Path, prefix: str, *, write_files: bool
) -> list[dict[str, Any]]:
    arts: list[dict[str, Any]] = [
        {"rel_path": f"tests/{prefix}.bld", "bytes": 12000, "sha256": SHA_PREF_A}
    ]
    for suffix, blob in ISA_SPECS:
        rel = f"{prefix}_out/{prefix}{suffix}"
        if write_files:
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(blob)
        sha = "sha256:" + hashlib.sha256(blob).hexdigest()
        arts.append({"rel_path": rel, "bytes": len(blob), "sha256": sha})
    return arts


def build_hsm_receipt(root: Path, *, write_files: bool = False) -> dict[str, Any]:
    excerpt = json.dumps(
        {
            "schema": "wave153a-slice36-zeroc-threshold-hsm/1",
            "ok": True,
            "params": {"t": 3, "n": 5, "hsm_audit_root_hex": HEX64_A},
            "total_verified_zero_c_binaries": 25,
        }
    )
    return {
        "schema": "engine-receipt/1",
        "verdict": "MATCH",
        "digests": {
            "claim_sha256": SHA_PREF_A,
            "subject_sha256": SHA_PREF_A,
            "envelope_sha256": SHA_PREF_A,
        },
        "oracle": {"exit_code": 0, "stdout_excerpt": excerpt},
        "subject": {
            "engine": "buildlang",
            "task_id": "wave153a-slice36-zeroc-threshold-hsm",
            "artifacts": _make_slice_artifacts(root, "hsm", write_files=write_files),
        },
    }


def build_raid_receipt(root: Path, *, write_files: bool = False) -> dict[str, Any]:
    excerpt = json.dumps(
        {
            "schema": "wave161b-slice37-zeroc-erasure-raid-fs/1",
            "ok": True,
            "params": {
                "k": 4,
                "m": 2,
                "healed_patterns": 15,
                "raid_merkle_root_hex": HEX64_B,
            },
            "total_verified_zero_c_binaries": 25,
        }
    )
    return {
        "schema": "engine-receipt/1",
        "verdict": "MATCH",
        "digests": {
            "claim_sha256": SHA_PREF_B,
            "subject_sha256": SHA_PREF_B,
            "envelope_sha256": SHA_PREF_B,
        },
        "oracle": {"exit_code": 0, "stdout_excerpt": excerpt},
        "subject": {
            "engine": "buildlang",
            "task_id": "wave161b-slice37-zeroc-erasure-raid-fs",
            "artifacts": _make_slice_artifacts(root, "raid", write_files=write_files),
        },
    }


def _build_gpu520_manifest() -> dict[str, Any]:
    targets = ("wgsl", "hlsl", "msl", "spirv", "glsl")
    shaders = [
        {
            "kernel": f"kernel_{i:03d}",
            "target": t,
            "shader_bytes": 4000,
            "shader_sha256": HEX64_A,
            "cert_sha256": HEX64_B,
            "rewrites": 7,
            "verify_cert": "PASS",
        }
        for i in range(104)
        for t in targets
    ]
    return {
        "schema": "buildlang-workstation-gpu-520pack/1",
        "license": "MIT",
        "unique_kernels": 104,
        "gpu_targets": 5,
        "total_certified_shaders": 520,
        "per_target_counts": {t: 104 for t in targets},
        "total_shader_bytes": 520 * 4000,
        "total_superopt_rewrites": 520 * 7,
        "shaders": shaders,
    }


def _build_gpu520_report() -> dict[str, Any]:
    return {
        "schema": "wave163a-gpu-520pack-quingentennial/1",
        "ok": True,
        "verdict": "PASS",
        "new_kernels": 8,
        "targets": 5,
        "new_certified_shaders": 40,
        "combined_520pack_shaders": 520,
        "combined_unique_kernels": 104,
        "combined_520pack_rewrites": 520 * 7,
        "combined_520pack_bytes": 520 * 4000,
        "validation_counts": {
            "verify_cert": 40,
            "dxc": 8,
            "glslang": 8,
            "spirv_val_direct": 8,
            "spirv_val_glsl": 8,
            "spirv_val_naga": 8,
            "naga_wgsl": 8,
            "naga_msl31": 8,
            "msl_spec": 8,
        },
        "planted_controls": {
            "ctrl1": {"rejected": True},
            "ctrl2": {"rejected": True},
            "ctrl3": {"rejected": True},
        },
        "controls_caught": 3,
    }


def build_gpu520_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    return _build_gpu520_manifest(), _build_gpu520_report()


def _build_rlvr_v14() -> dict[str, Any]:
    cats = {f"cat_{i:02d}": 32 for i in range(33)}
    cats["planted_negative_trap"] = 64
    cats["buildlang_synthesis"] = 80
    cats["superopt_equivalence"] = 80
    return {
        "schema": "jfc3p-rlvr-pack/v14",
        "license": "MIT",
        "push_to_hub": False,
        "counts": {
            "categories": 36,
            "total_tasks": 1280,
            "train_tasks": 1104,
            "eval_tasks": 176,
            "new_v14_tasks": 128,
            "v13_preserved_tasks": 1152,
        },
        "category_counts": cats,
        "artifacts": {
            "jfc3p_14b_oracle_v14_mit.jsonl": {
                "bytes": 1000,
                "rows": 1280,
                "sha256": SHA_PREF_A,
            },
            "train_rlvr_v14.jsonl": {"bytes": 800, "rows": 1104, "sha256": SHA_PREF_A},
            "eval_rlvr_v14.jsonl": {"bytes": 200, "rows": 176, "sha256": SHA_PREF_A},
            "JFC3P_14B_Oracle_v14_Colab_H100_Ready.ipynb": {
                "bytes": 4093,
                "sha256": SHA_PREF_A,
            },
        },
        "immutable_pins": {f"pin_{i}": SHA_PREF_B for i in range(5)},
    }


def _build_paper8() -> dict[str, Any]:
    return {
        "schema": "harperz9.wave160a-arxiv-zenodo-paper8/1",
        "paper_license": "CC-BY-4.0",
        "code_licenses": ["MIT", "AGPL-3.0-only"],
        "orcid": "0009-0001-7175-5393",
        "send_policy": "STAGED_ON_DISK_ONLY_ZERO_EXTERNAL_UPLOADS",
        "prior_papers_and_packs_untouched": True,
        "arxiv_categories": ["cs.PL", "cs.CR", "cs.OS"],
        "verified_catalogue_ids": [
            68857,
            68877,
            68903,
            68920,
            68925,
            68929,
            68941,
            68945,
            68948,
        ],
        "deliverables": {
            "paper_words": 1263,
            "paper_pages": 6,
            "paper_bytes": 654006,
            "page_pngs": [f"PAGE{i}.png" for i in range(1, 7)],
        },
    }


def build_rlvr_and_paper8() -> tuple[dict[str, Any], dict[str, Any]]:
    return _build_rlvr_v14(), _build_paper8()
