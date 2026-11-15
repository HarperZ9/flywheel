"""Rollout-receipt proof packets: wedge #6 (RL / post-training runs).

A post-training run -> a proof packet that keeps reward score, verifier verdict,
admission policy, and promotion decision as SEPARATE records, with default-deny
promotion (promote only on a MATCH verifier + an allow admission). Harvested from
research/rl-scaling-receipt-spine.md. Zero-dep, crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_rollout_receipt_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_rollout_receipt_packet,
    validate_rollout_receipt_packet_file,
)
from .report import render_report

__all__ = [
    "build_rollout_receipt_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_rollout_receipt_packet",
    "validate_rollout_receipt_packet_file",
]
