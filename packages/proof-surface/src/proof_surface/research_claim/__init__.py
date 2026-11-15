"""Research-claim proof packets (pipeline-math++): wedge #3.

Source refs, a formal statement, prover/checker attempts, verification checks, a
re-derivable verdict, and a promotion-ladder rung -- where a failed or
unverifiable attempt still produces a valid, useful packet. Marks unverified
ambition as UNVERIFIABLE, never as solved.
"""

from __future__ import annotations

from .builder import build_research_claim_packet, to_crucible_inputs
from .report import render_report
from .packet import (
    PACKET_VERSION,
    PROMOTIONS,
    load_packet,
    validate_research_claim_packet,
    validate_research_claim_packet_file,
)

__all__ = [
    "build_research_claim_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "PROMOTIONS",
    "load_packet",
    "validate_research_claim_packet",
    "validate_research_claim_packet_file",
]
