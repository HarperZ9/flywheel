# SPDX-License-Identifier: MIT
"""Verifier for Quingentennial 520/520 GPU shaders, RLVR v14, and Paper #8 Octet."""

from harness.gpu_shader_520_gate.gpu520_models import (
    Gpu520Manifest,
    Gpu520Report,
    Gpu520ShaderEntry,
    Paper8Manifest,
    QuingentennialBundle,
    RlvrV14Manifest,
)
from harness.gpu_shader_520_gate.gpu520_oracle import (
    Gpu520Verdict,
    main,
    verify_gpu_520_bundle,
    verify_gpu_520_files,
)
from harness.gpu_shader_520_gate.gpu520_parser import (
    parse_gpu_520_manifest,
    parse_gpu_520_report,
    parse_paper8_manifest,
    parse_rlvr_v14_manifest,
)

__all__ = [
    "Gpu520Manifest",
    "Gpu520Report",
    "Gpu520ShaderEntry",
    "Gpu520Verdict",
    "Paper8Manifest",
    "QuingentennialBundle",
    "RlvrV14Manifest",
    "main",
    "parse_gpu_520_manifest",
    "parse_gpu_520_report",
    "parse_paper8_manifest",
    "parse_rlvr_v14_manifest",
    "verify_gpu_520_bundle",
    "verify_gpu_520_files",
]
