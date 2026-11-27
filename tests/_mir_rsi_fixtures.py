# SPDX-License-Identifier: MIT
"""Fixture builders for mir_assurance_gate and rsi_pareto_gate tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SHA40 = "a" * 40
HEX16 = "0123456789abcdef"
CORE_FILES = ("boot.bl", "mm.bl", "ipc.bl", "sched.bl", "syscall.bl")


def build_effect_manifest() -> dict[str, Any]:
    mods = [
        {
            "file": f,
            "functions": 10,
            "pure_functions": 9,
            "module_effects": ["console"],
            "zero_egress": True,
            "manifest_sha256_prefix": HEX16,
        }
        for f in CORE_FILES
    ]
    return {
        "schema": "buildlang.effect-manifest/v1",
        "commit_sha": SHA40,
        "lib_tests_passed": 1177,
        "integration_tests_passed": 4,
        "buildos_core_sweep": {
            "denied_effects": ["fs", "net", "exec", "unsafe"],
            "files_audited": 5,
            "files_passed": 5,
            "total_functions": 50,
            "pure_functions": 45,
            "zero_egress_all": True,
            "modules": mods,
        },
    }


def build_wcet_manifest() -> dict[str, Any]:
    mods = [
        {
            "file": f,
            "functions": 10,
            "max_frame_bytes": 1024,
            "max_stack_bytes": 2048,
            "max_wcet_cost": 400,
            "stack_bounded": True,
            "has_recursion": False,
            "manifest_sha256_prefix": HEX16,
        }
        for f in CORE_FILES
    ]
    return {
        "schema": "buildlang.wcet-manifest/v1",
        "commit_sha": SHA40,
        "lib_tests_passed": 1180,
        "integration_tests_passed": 4,
        "buildos_core_sweep": {
            "single_frame_limit_bytes": 2048,
            "page_budget_bytes": 4096,
            "files_audited": 5,
            "files_passed_4096": 5,
            "total_functions": 50,
            "functions_under_2048_frame": 50,
            "recursion_free_all": True,
            "max_single_frame_bytes": 1024,
            "peak_transitive_stack_bytes": 2048,
            "modules": mods,
        },
    }


def build_ct_manifest() -> dict[str, Any]:
    mods = [
        {
            "file": f,
            "functions": 10,
            "secret_sources": 2,
            "violations": 0,
            "constant_time_verified": True,
            "manifest_sha256_prefix": HEX16,
        }
        for f in CORE_FILES
    ]
    return {
        "schema": "buildlang.ct-manifest/v1",
        "commit_sha": SHA40,
        "lib_tests_passed": 1190,
        "integration_tests_passed": 4,
        "planted_side_channel_controls_caught": 3,
        "buildos_core_sweep": {
            "files_audited": 5,
            "files_passed": 5,
            "total_functions": 50,
            "total_violations": 0,
            "constant_time_verified_all": True,
            "modules": mods,
        },
    }


def build_det_manifest() -> dict[str, Any]:
    mods = [
        {
            "file": f,
            "functions": 10,
            "deterministic_functions": 10,
            "violations": 0,
            "bit_exact_deterministic": True,
            "manifest_sha256_prefix": HEX16,
        }
        for f in CORE_FILES
    ]
    return {
        "schema": "buildlang.det-manifest/v1",
        "commit_sha": SHA40,
        "lib_tests_passed": 1195,
        "integration_tests_passed": 4,
        "planted_nondeterminism_hazards_caught": 3,
        "buildos_core_sweep": {
            "files_audited": 5,
            "files_passed": 5,
            "total_functions": 50,
            "deterministic_functions": 50,
            "total_violations": 0,
            "bit_exact_deterministic_all": True,
            "modules": mods,
        },
    }


def build_mir_payloads() -> dict[str, dict[str, Any]]:
    return {
        "effect": build_effect_manifest(),
        "wcet": build_wcet_manifest(),
        "ct": build_ct_manifest(),
        "det": build_det_manifest(),
    }


def build_rsi_payload() -> dict[str, Any]:
    return {
        "schema": "wave149b-rsi-pareto-orchestrator/1",
        "ok": True,
        "verdict": "PASS",
        "wasm_bytes": 9261,
        "cycles": 100,
        "lanes": 8,
        "metrics": {
            "initial_score": 3.39,
            "final_score": 10.237,
            "compound_gain_x": 10.237 / 3.39,
            "goodhart_traps_total": 40.0,
            "goodhart_traps_blocked": 40.0,
            "regressions": 0.0,
            "monotonic_ok": 1.0,
            "failures": 0.0,
        },
        "parity": {"max_3way_err": 3.628e-13},
        "controls": {
            "ctrl1_goodhart_rolled_back": True,
            "ctrl2_nonpos_budget_trapped": True,
            "ctrl3_forged_superopt_cert_rejected": True,
        },
        "controls_caught": 3,
        "controls_total": 3,
    }


def build_wasm_pack(root: Path, *, write_wasm: bool = False) -> dict[str, Any]:
    blob = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 64
    sha = hashlib.sha256(blob).hexdigest()
    mods = []
    for idx in range(100):
        rel = f"modules/demo_{idx:03d}.wasm"
        if write_wasm:
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(blob)
        mods.append(
            {
                "pack": 1,
                "idea_id": f"IDEA-{idx:03d}",
                "slug": f"demo-{idx:03d}",
                "wasm_path": rel,
                "wasm_bytes": len(blob),
                "wasm_sha256": sha,
                "license": "MIT",
            }
        )
    return {
        "schema": "site-dropin-wasm-100pack/1",
        "license": "MIT",
        "module_count": 100,
        "zero_import_count": 16,
        "total_bytes": 100 * len(blob),
        "under_1_25mb": True,
        "modules": mods,
    }


def write_mir_files(
    tmp_path: Path, payloads: dict[str, dict[str, Any]]
) -> tuple[Path, Path, Path, Path]:
    keys = ("effect", "wcet", "ct", "det")
    ps = [tmp_path / f"{k}.json" for k in keys]
    for k, p in zip(keys, ps, strict=True):
        p.write_text(json.dumps(payloads[k]), encoding="utf-8")
    return ps[0], ps[1], ps[2], ps[3]
