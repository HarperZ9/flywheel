"""Articulate: a local writing-quality and AI-tell detection and editing tool.

The core detector runs standard-library-only with no network call. The optional
editor layer supports model backends and deterministic edits. The register-adaptive
profile system decides which findings gate.
"""
from . import genres, profiles
from .detector import (GATE_TIERS, analyze_blocks, binary_reason, check_text,
                       scan_lines, segment_blocks)

__version__ = "0.19.1"
__all__ = ["check_text", "scan_lines", "analyze_blocks", "segment_blocks",
           "binary_reason", "profiles", "genres", "GATE_TIERS", "__version__"]
