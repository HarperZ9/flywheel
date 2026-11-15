"""Conservation proof packets: wedge #9 (invariant conservation).

A claimed transformation conserves a declared invariant, proven by independent
witnesses (algebraic residual / numeric drift) AND falsified by a required
negative fixture that must break it. Domain-general: mass/energy balance,
refactor-preserves-total, RL return, optimization objective. The load-bearing
gate (dogfood 0105/0106/0107): a verifier that cannot fail on a known-bad input
is not a verifier. Zero-dep, crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_conservation_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_conservation_packet,
    validate_conservation_packet_file,
)
from .report import render_report

__all__ = [
    "build_conservation_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_conservation_packet",
    "validate_conservation_packet_file",
]
