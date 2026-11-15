"""Agent-action proof packet: trace -> unified anatomy packet -> verdict -> report.

The rank-1 wedge. A self-contained, stdlib-only submodule that turns an agent's
execution trace into a portable, re-checkable proof packet: what was claimed,
what sources it rested on, which material actions ran, why each was admitted,
their side-effect class / idempotency / compensation, the outputs, and a
MATCH/DRIFT/UNVERIFIABLE verdict. "Telemetry explains a run; a receipt justifies
an action."
"""

from __future__ import annotations

from .builder import build_agent_action_packet
from .importer import ActionRecord, ContextSpan, Flagged, TraceImport, import_trace
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_agent_action_packet,
    validate_agent_action_packet_file,
)
from .report import render_report
from .verdicts import attach_verdicts, to_crucible_inputs, verdict_for_measurement

__all__ = [
    "render_report",
    "ActionRecord",
    "ContextSpan",
    "Flagged",
    "TraceImport",
    "import_trace",
    "build_agent_action_packet",
    "PACKET_VERSION",
    "load_packet",
    "validate_agent_action_packet",
    "validate_agent_action_packet_file",
    "attach_verdicts",
    "to_crucible_inputs",
    "verdict_for_measurement",
]
