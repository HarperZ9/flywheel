"""Visual Truth Kit: read-only visual/color/display measurement proof packets.

Wedge #2. Joins an artifact digest, declared color assumptions, measured metrics
(Build Color / Calibrate Pro shaped, ingested as data), honest display caveats,
and a re-derivable verdict. Non-mutating by construction: it records and verifies
measurements, it never applies a LUT/ICC/DDC change or claims hardware
calibration it did not perform.
"""

from __future__ import annotations

from .builder import build_visual_measurement_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_visual_measurement_packet,
    validate_visual_measurement_packet_file,
)
from .report import render_report

__all__ = [
    "build_visual_measurement_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_visual_measurement_packet",
    "validate_visual_measurement_packet_file",
]
