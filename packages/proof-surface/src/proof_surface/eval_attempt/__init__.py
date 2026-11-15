"""Eval-attempt proof packets: wedge #7 (single benchmark attempt).

A single benchmark attempt -> a proof packet binding the benchmark authority, the
prompt/model/tool-use it ran with, a replay ref, an honest boundary block, and a
re-derivable verdict. The honesty gate: a `correct` outcome with ground-truth
access is contamination, not a pass. Harvested from dogfood pass 0085/0096.
Zero-dep, crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_eval_attempt_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_eval_attempt_packet,
    validate_eval_attempt_packet_file,
)
from .report import render_report

__all__ = [
    "build_eval_attempt_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_eval_attempt_packet",
    "validate_eval_attempt_packet_file",
]
