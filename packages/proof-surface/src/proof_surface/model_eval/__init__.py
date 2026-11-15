"""Model-eval proof packets (model-foundry / eval forge): wedge #4.

A model run + eval set + directional metrics + objective -> a re-derivable verdict
and a default-deny promotion decision (promote only if overall MATCH). Zero-dep,
crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_model_eval_packet, to_crucible_inputs
from .report import render_report
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_model_eval_packet,
    validate_model_eval_packet_file,
)

__all__ = [
    "build_model_eval_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_model_eval_packet",
    "validate_model_eval_packet_file",
]
