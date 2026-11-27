# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for the Bicentennial 200-Shader GPU Pack.

Verifies 40 MIT GPU compute kernels x 5 backends (200 shaders), Superopt V6
rewrite totals, external validator pass tags (dxc, glslangValidator, spirv-val,
naga), shader SHA-256 parity, and gpu_shader_200_attestation_sha256 sealing.
"""

from __future__ import annotations

from .gpu200_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .gpu200_oracle import (
    Gpu200GateReport,
    verify_gpu_200_pack,
    verify_gpu_200_pack_files,
)
from .manifest_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)
from .manifest_parser import (
    CertifiedShaderEntry,
    parse_gpu_200_manifest,
)
from .shader_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)
from .shader_guards import (
    REQUIRED_GPU_TARGETS,
    SHA256_HEX_RE,
    canonical_sha256_hex,
    is_passing_validator_tag,
    is_strict_finite_float,
    is_strict_int,
    normalize_sha256,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for the 200-shader 5-backend GPU "
    "compute manifest (MIT licensing, 5-target coverage, Superopt V6 rewrite "
    "totals, validator pass tags, and shader SHA-256 parity). Does not launch "
    "GPU drivers or external shader compilers."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "shader_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "manifest_parser": PARSER_HONEST_SCOPE_LIMIT,
    "gpu200_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "CertifiedShaderEntry",
    "Gpu200GateReport",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "REQUIRED_GPU_TARGETS",
    "SHA256_HEX_RE",
    "canonical_sha256_hex",
    "is_passing_validator_tag",
    "is_strict_finite_float",
    "is_strict_int",
    "normalize_sha256",
    "parse_gpu_200_manifest",
    "verify_gpu_200_pack",
    "verify_gpu_200_pack_files",
]
