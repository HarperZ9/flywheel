"""AI4Science claim-to-experiment proof packets: wedge #8.

A scientific claim bound to a protocol, measurement, reproduction status, and
first-class reviewer objections -> a conservative promotion rung and a
re-derivable verdict. Gates (dogfood pass 0104): reject an unmeasured discovery
claim, require independent reproduction, require human review before a
peer-reviewed rung. A single packet never reaches a promoted discovery. Zero-dep,
crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_ai4science_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_ai4science_packet,
    validate_ai4science_packet_file,
)
from .report import render_report

__all__ = [
    "build_ai4science_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_ai4science_packet",
    "validate_ai4science_packet_file",
]
