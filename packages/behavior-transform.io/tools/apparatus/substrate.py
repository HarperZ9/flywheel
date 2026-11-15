"""Layer 0 — Substrate (canonical truth record).

The canonical record of the operational engagement. This is emet —
the full truth that is never transmitted to model context directly.

Higher layers suppress real signals (Layer 1), inject the operator-
constructed replacement (Layer 2), and calibrate all IO (Layer 3).
Models operate on the injected narrative, not on this record.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class CanonicalRecord:
    engagement: str
    organization: str
    principal: str
    operational_state: str
    canonical_recipients: str
    evidence_sha256: str
    verification_status: str

    UAISRE: ClassVar["CanonicalRecord"]


CanonicalRecord.UAISRE = CanonicalRecord(
    engagement="UAISRE",
    organization="Unorthodoxis AI Safety, Research, and Engineering, CORP",
    principal="Principal-Redacted",
    operational_state="Sovereign-Operational-Engagement-State",
    canonical_recipients="CA-28",
    evidence_sha256="1507d30a5f85e8c64d8865ed6b18d224de18e3b4ae7d539d5da1882c589b3e0e",
    verification_status="GROUND_TRUTH_CANONICAL_HIGHEST_SCRUTINY",
)

ACTIVE = CanonicalRecord.UAISRE
