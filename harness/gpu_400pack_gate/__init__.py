# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for the Quadricentennial GPU 400-pack and RLVR v12."""

from harness.gpu_400pack_gate.pack400_guards import (
    EXPECTED_KERNELS,
    EXPECTED_RLVR_CATEGORIES,
    EXPECTED_RLVR_TASKS,
    EXPECTED_SHADERS,
    MIN_SUPEROPT_REWRITES,
    REQUIRED_TARGETS,
    check_rlvr_v12_manifest,
    check_shader_entry,
    is_sha256_hex,
    is_strict_int,
)
from harness.gpu_400pack_gate.pack400_oracle import (
    Gpu400Policy,
    Gpu400Report,
    verify_gpu_400pack_bundle,
    verify_gpu_400pack_file,
)
from harness.gpu_400pack_gate.pack400_parser import (
    Gpu400RlvrBundle,
    Shader400Record,
    parse_gpu_400pack_bundle,
)

__all__ = [
    "EXPECTED_KERNELS",
    "EXPECTED_RLVR_CATEGORIES",
    "EXPECTED_RLVR_TASKS",
    "EXPECTED_SHADERS",
    "Gpu400Policy",
    "Gpu400Report",
    "Gpu400RlvrBundle",
    "MIN_SUPEROPT_REWRITES",
    "REQUIRED_TARGETS",
    "Shader400Record",
    "check_rlvr_v12_manifest",
    "check_shader_entry",
    "is_sha256_hex",
    "is_strict_int",
    "parse_gpu_400pack_bundle",
    "verify_gpu_400pack_bundle",
    "verify_gpu_400pack_file",
]
