"""The observation contract -- the membrane's externalized, witnessed artifact.

An organ does not return a belief; it returns an Observation: a value the
hardware/filesystem actually produced, stamped with provenance (what was read,
its digest, when, and how confident the read itself is).  This is deliberately
wire-compatible with provenance-sensorium's model so the two repos compose
through the shared JSON shape without importing each other.

Three membrane invariants are encoded here, not asserted:
  * Externalized   -- every Observation serialises to JSON (to_dict / from_dict).
  * Witnessed      -- provenance.digest is the SHA-256 of the witnessed bytes,
                     full width, re-derivable by any host.
  * Advisory       -- Status is a report, never an authority grant; there is no
                     TRUSTED/APPROVED/AUTHORIZED status.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Advisory status of an observation.  No authority-shaped value exists."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    NEEDS_HUMAN = "needs-human"
    UNVERIFIED = "unverified"


def sha256_hex(payload: bytes) -> str:
    """Full-width (64 hex char) SHA-256 of bytes.  No truncation -- the digest is
    the re-derivable trust anchor, so it must be the whole hash."""
    return hashlib.sha256(payload).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Provenance:
    """How an observation was obtained.  `digest` is sha256: + 64 hex chars."""

    source: str
    digest: str
    timestamp: str
    confidence: str
    command: str | None = None

    @classmethod
    def witness_bytes(
        cls,
        source: str,
        payload: bytes,
        confidence: str,
        *,
        command: str | None = None,
        timestamp: str | None = None,
    ) -> "Provenance":
        return cls(
            source=source,
            digest="sha256:" + sha256_hex(payload),
            timestamp=timestamp or _utc_now_iso(),
            confidence=confidence,
            command=command,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "digest": self.digest,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }
        if self.command is not None:
            data["command"] = self.command
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Provenance":
        return cls(
            source=str(data["source"]),
            digest=str(data["digest"]),
            timestamp=str(data["timestamp"]),
            confidence=str(data["confidence"]),
            command=data.get("command"),
        )


@dataclass(frozen=True)
class Observation:
    """A witnessed fact emitted by an organ.

    organ      -- the organ that produced it.
    subject    -- what was observed (a path, an artifact id).
    summary    -- short human-readable description.
    status     -- advisory Status.
    provenance -- how it was witnessed (digest, timestamp, confidence).
    data       -- structured, re-derivable measurements (dims, hashes, ...).
    """

    organ: str
    subject: str
    summary: str
    status: Status
    provenance: Provenance
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "organ": self.organ,
            "subject": self.subject,
            "summary": self.summary,
            "status": self.status.value,
            "provenance": self.provenance.to_dict(),
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(
            organ=str(data["organ"]),
            subject=str(data["subject"]),
            summary=str(data["summary"]),
            status=Status(str(data["status"])),
            provenance=Provenance.from_dict(data["provenance"]),
            data=dict(data.get("data", {})),
        )
