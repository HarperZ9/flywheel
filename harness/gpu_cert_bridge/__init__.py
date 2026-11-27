# SPDX-License-Identifier: MIT
"""Pure-stdlib 5-target GPU shader certificate and superoptimizer bridge.

Verifies buildlang.gpu-tv-cert/v1 shader certificates, embedded
buildlang.superopt-cert/v1 monotone MIR cost chains, and complete 5-target
matrix coverage across wgsl, hlsl, msl, spirv, and glsl.
"""

from __future__ import annotations

from .matrix_gate import (
    HONEST_SCOPE_LIMIT as MATRIX_HONEST_SCOPE_LIMIT,
)
from .matrix_gate import (
    GpuMatrixReport,
    KernelMatrixEntry,
    discover_kernel_certs,
    verify_gpu_cert_matrix,
)
from .shader_cert import (
    GPU_CERT_SCHEMA,
    REQUIRED_GPU_TARGETS,
    TARGET_SHADER_EXT,
    ShaderCertReport,
    is_hex64,
    sha256_hex,
    verify_shader_cert,
    verify_shader_cert_files,
)
from .shader_cert import (
    HONEST_SCOPE_LIMIT as SHADER_HONEST_SCOPE_LIMIT,
)
from .superopt_chain import (
    HONEST_SCOPE_LIMIT as SUPEROPT_HONEST_SCOPE_LIMIT,
)
from .superopt_chain import (
    SUPEROPT_CERT_SCHEMA,
    SuperoptChainReport,
    extract_superopt_cert,
    verify_superopt_cert,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib verification bridge for BuildLang GPU shader "
    "translation-validation certificates and Superoptimizer V6 MIR cost "
    "chains. Does not compile BuildLang sources, run e-graph/SMT provers, or "
    "execute emitted GPU shaders on hardware."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "shader_cert": SHADER_HONEST_SCOPE_LIMIT,
    "superopt_chain": SUPEROPT_HONEST_SCOPE_LIMIT,
    "matrix_gate": MATRIX_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "GPU_CERT_SCHEMA",
    "GpuMatrixReport",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "KernelMatrixEntry",
    "REQUIRED_GPU_TARGETS",
    "SUPEROPT_CERT_SCHEMA",
    "ShaderCertReport",
    "SuperoptChainReport",
    "TARGET_SHADER_EXT",
    "discover_kernel_certs",
    "extract_superopt_cert",
    "is_hex64",
    "sha256_hex",
    "verify_gpu_cert_matrix",
    "verify_shader_cert",
    "verify_shader_cert_files",
    "verify_superopt_cert",
]
