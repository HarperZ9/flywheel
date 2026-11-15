"""Control-certificate proof packets: wedge #10 (decrease/stability certificate).

A controller or iterative process claiming stability, termination, or
convergence carries a declared certificate (lyapunov, ranking-function,
contraction-metric, mpc-feasibility), witnessed conditions with real
residuals, a REQUIRED negative fixture that must violate the certificate, and
an explicit sim-to-real boundary (hardware validity is never claimable from
simulation-only evidence). Grounded in dogfood passes 0112/0113 and the
operator's robotics/cybernetics lane. Decrease is not constancy: conserved
quantities belong to the conservation wedge. Zero-dep, crucible as an
optional peer.
"""

from __future__ import annotations

from .builder import build_control_certificate_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_control_certificate_packet,
    validate_control_certificate_packet_file,
)
from .report import render_report

__all__ = [
    "build_control_certificate_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_control_certificate_packet",
    "validate_control_certificate_packet_file",
]
