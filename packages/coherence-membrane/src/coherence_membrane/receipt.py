"""Signed observation receipts -- the external anchor across the read->write seam.

A bare Observation's SHA-256 is keyless self-consistency: re-derivable integrity,
but not tamper-evidence against an adversary who recomputes it. The honest fix is
an EXTERNAL anchor -- and this is where it lives, at the seam between perception and
action. A WitnessReceipt wraps an Observation's witnessed facts into a stable,
serialisable record with a content hash (its `anchor`). The operator pins that
anchor out-of-band (and may sign it); later, verify_receipt re-derives the anchor
and checks it against the pinned value.

The discipline, mirroring proof-surface's delegation chain:
  * The receipt holds NO key and signs nothing. Signing is the operator's act,
    supplied as a verifier callback -- the receipt only carries the material.
  * verify_receipt is a closed lattice, fail-closed:
      VALID         anchor matches the pinned value (or a supplied signature
                    verifier confirms it),
      DRIFT         the receipt's content no longer hashes to the pinned anchor --
                    the facts changed,
      UNVERIFIABLE  no pinned anchor and no verifier -- self-consistent only, which
                    is honestly NOT tamper-evidence.
  * A verifier that raises is treated as DRIFT (fail-closed), never VALID.

So: read-gate witnesses -> emit_receipt -> operator pins/signs the anchor ->
write-gate (or any consumer) verifies the receipt against that anchor before
acting. The anchor is the thing keyless hashes always pointed at.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .observation import Observation, sha256_hex

RECEIPT_VERSION = "0.1"

VALID = "VALID"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"
RECEIPT_VERDICTS = frozenset({VALID, DRIFT, UNVERIFIABLE})

# Observation.data keys carried as witnessed facts (re-derivable measurements).
_FACT_KEYS = (
    "identity_sha256",
    "perceptual_hash",
    "perceptual_audio_hash",
    "canonical_sha256",
    "region_hashes",
    "width",
    "height",
    "format",
)


@dataclass(frozen=True)
class WitnessReceipt:
    """A stable, serialisable record of an Observation's witnessed facts, whose
    content hash (`anchor`) is the external pin point."""

    receipt_version: str
    organ: str
    subject: str
    digest: str  # provenance digest: "sha256:" + 64 hex
    timestamp: str
    confidence: str
    facts: dict[str, Any] = field(default_factory=dict)

    def _canonical_content(self) -> bytes:
        """The receipt's content in canonical form (anchor input). Excludes the
        anchor itself; sorted keys + compact separators so it is re-derivable."""
        body = {
            "receipt_version": self.receipt_version,
            "organ": self.organ,
            "subject": self.subject,
            "digest": self.digest,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "facts": self.facts,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")

    def anchor(self) -> str:
        """The pinnable content hash: SHA-256 of the canonical content (64 hex)."""
        return sha256_hex(self._canonical_content())

    def to_dict(self) -> dict[str, Any]:
        data = {
            "receipt_version": self.receipt_version,
            "organ": self.organ,
            "subject": self.subject,
            "digest": self.digest,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "facts": self.facts,
        }
        data["anchor"] = self.anchor()  # convenience; recomputed on verify, never trusted
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WitnessReceipt":
        return cls(
            receipt_version=str(d["receipt_version"]),
            organ=str(d["organ"]),
            subject=str(d["subject"]),
            digest=str(d["digest"]),
            timestamp=str(d["timestamp"]),
            confidence=str(d["confidence"]),
            facts=copy.deepcopy(d.get("facts", {})),  # snapshot: never alias the source
        )


def emit_receipt(observation: Observation) -> WitnessReceipt:
    """Build a WitnessReceipt from an Observation's witnessed provenance + facts."""
    # Deep-copy so the receipt is a stable snapshot -- a nested fact value (e.g. a
    # region_hashes list) must not alias the source and let the anchor drift.
    facts = copy.deepcopy({k: observation.data[k] for k in _FACT_KEYS if k in observation.data})
    return WitnessReceipt(
        receipt_version=RECEIPT_VERSION,
        organ=observation.organ,
        subject=observation.subject,
        digest=observation.provenance.digest,
        timestamp=observation.provenance.timestamp,
        confidence=observation.provenance.confidence,
        facts=facts,
    )


@dataclass(frozen=True)
class ReceiptVerdict:
    verdict: str  # VALID / DRIFT / UNVERIFIABLE
    reason: str


def verify_receipt(
    receipt: WitnessReceipt,
    *,
    pinned_anchor: str | None = None,
    signature_verifier: Callable[[WitnessReceipt], bool] | None = None,
) -> ReceiptVerdict:
    """Verify a receipt against an external anchor, fail-closed.

    With a `signature_verifier` (the operator's crypto), a True result is VALID
    and a False/raising result is DRIFT -- non-repudiable identity, the operator's
    to provide. With a `pinned_anchor`, the receipt's re-derived anchor must equal
    it (VALID) or it has changed (DRIFT). With neither, the result is UNVERIFIABLE:
    the receipt is self-consistent but that is not tamper-evidence.

    If BOTH are supplied, the `signature_verifier` takes sole precedence and
    `pinned_anchor` is not checked -- the operator's verifier is the authority and
    may bind the anchor itself; they are alternatives, not a conjunction.
    """
    if signature_verifier is not None:
        try:
            ok = signature_verifier(receipt)
        except Exception:
            return ReceiptVerdict(DRIFT, "signature verifier raised -- treated as invalid (fail-closed)")
        if ok:
            return ReceiptVerdict(VALID, "signature verified by the operator's verifier")
        return ReceiptVerdict(DRIFT, "signature verifier rejected the receipt")

    if pinned_anchor is None:
        return ReceiptVerdict(
            UNVERIFIABLE,
            "no pinned anchor and no signature verifier -- the receipt is "
            "self-consistent but that is not tamper-evidence against recomputation",
        )

    if receipt.anchor() == pinned_anchor:
        return ReceiptVerdict(VALID, "re-derived anchor matches the pinned anchor")
    return ReceiptVerdict(
        DRIFT, "re-derived anchor does not match the pinned anchor -- the receipt's "
        "content changed since it was pinned",
    )
