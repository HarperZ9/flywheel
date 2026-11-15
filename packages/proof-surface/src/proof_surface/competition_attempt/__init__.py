"""Competition-attempt proof packets: wedge #11 (competition/judge attempt).

A single competition attempt binds the challenge to a source-pinned judge
repository observation (repo ref, 40-hex head sha, observed file count, files
digest), discloses hosted-model usage with the eval-attempt hermeticity rule
verbatim, records how the answer was extracted (a non-boxed extraction must
carry an injection check; an unrendered template marker is rejected), and
carries a closed certificate ladder (informal-model-output,
machine-checked-proof, finite-counterexample, judge-verdict). A fenced layer
must cite its probe; the verdict may only cite EXECUTED layers; MATCH is only
derivable from an executed, passing judge verdict. Grounded in the SAIR
competition dogfood cluster (0136/0137/0138/0139). Zero-dep, crucible as an
optional peer.
"""

from __future__ import annotations

from .builder import build_competition_attempt_packet, to_crucible_inputs
from .packet import (
    PACKET_VERSION,
    load_packet,
    validate_competition_attempt_packet,
    validate_competition_attempt_packet_file,
)
from .report import render_report

__all__ = [
    "build_competition_attempt_packet",
    "to_crucible_inputs",
    "render_report",
    "PACKET_VERSION",
    "load_packet",
    "validate_competition_attempt_packet",
    "validate_competition_attempt_packet_file",
]
