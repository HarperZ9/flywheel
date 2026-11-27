# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for the 240-shader 5-backend GPU compute suite."""

from harness.gpu_240pack_gate.pack240_guards import (
    EXPECTED_KERNELS,
    EXPECTED_SHADERS,
    MIN_SUPEROPT_REWRITES,
    REQUIRED_TARGETS,
    REQUIRED_VALIDATORS,
    check_planted_shader_controls,
    check_shader_entry,
    check_validation_counts,
    is_sha256_hex,
    is_strict_int,
)
from harness.gpu_240pack_gate.pack240_oracle import (
    Gpu240Policy,
    Gpu240Report,
    verify_gpu_240pack_bundle,
    verify_gpu_240pack_file,
)
from harness.gpu_240pack_gate.pack240_parser import (
    Gpu240Bundle,
    Shader240Record,
    parse_gpu_240pack_manifest,
)

__all__ = [
    "EXPECTED_KERNELS",
    "EXPECTED_SHADERS",
    "Gpu240Bundle",
    "Gpu240Policy",
    "Gpu240Report",
    "MIN_SUPEROPT_REWRITES",
    "REQUIRED_TARGETS",
    "REQUIRED_VALIDATORS",
    "Shader240Record",
    "check_planted_shader_controls",
    "check_shader_entry",
    "check_validation_counts",
    "is_sha256_hex",
    "is_strict_int",
    "parse_gpu_240pack_manifest",
    "verify_gpu_240pack_bundle",
    "verify_gpu_240pack_file",
]
