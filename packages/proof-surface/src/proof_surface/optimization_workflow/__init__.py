"""Optimization-workflow proof packets: wedge #5.

A problem (objective + constraints) + an exact baseline + a solver branch -> a
re-derivable verdict that the solver's best feasible objective matches the exact
optimum, with an honest no-quantum/no-hardware-overclaim boundary. Quantum
optimization is the lead demo; the primitive is domain-general. Zero-dep,
crucible as an optional peer.
"""

from __future__ import annotations

from .builder import build_optimization_workflow_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_optimization_workflow_packet,
    validate_optimization_workflow_packet_file,
)
from .report import render_report

__all__ = [
    "build_optimization_workflow_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_optimization_workflow_packet",
    "validate_optimization_workflow_packet_file",
]
