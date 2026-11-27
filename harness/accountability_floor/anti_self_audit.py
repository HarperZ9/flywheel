# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N49 Anti-Self-Investigation Out-of-Band FIPS 180-4 SHA-256 Audit Chain.

Refuses self-attestation (proposer_id == verifier_id) fail-closed and seals
every out-of-band verified claim into a canonical SHA-256 hash chain that can
be re-verified offline with zero external dependencies.
Pure Python standard library only.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

GENESIS_DIGEST = "sha256:" + ("0" * 64)


class SelfAttestationError(ValueError):
    """Raised fail-closed when proposer and verifier identities are not independent."""


@dataclass(frozen=True)
class OutOfBandRecord:
    """Single immutable out-of-band attested claim link."""

    seq: int
    proposer_id: str
    verifier_id: str
    claim_digest: str
    verdict: str
    prev_sha256: str
    record_sha256: str


def _canonical_record_sha256(
    seq: int,
    proposer_id: str,
    verifier_id: str,
    claim_digest: str,
    verdict: str,
    prev_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "seq": seq,
            "proposer_id": proposer_id,
            "verifier_id": verifier_id,
            "claim_digest": claim_digest,
            "verdict": verdict,
            "prev_sha256": prev_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class OutOfBandChain:
    """Append-only N49 SHA-256 audit chain enforcing proposer_id != verifier_id."""

    def __init__(self) -> None:
        self._records: list[OutOfBandRecord] = []

    @property
    def records(self) -> tuple[OutOfBandRecord, ...]:
        return tuple(self._records)

    @property
    def head_sha256(self) -> str:
        return self._records[-1].record_sha256 if self._records else GENESIS_DIGEST

    def append(
        self,
        proposer_id: str,
        verifier_id: str,
        claim_digest: str,
        verdict: str = "PASS",
    ) -> OutOfBandRecord:
        p_norm = proposer_id.strip()
        v_norm = verifier_id.strip()
        if not p_norm or not v_norm:
            raise SelfAttestationError("proposer_id and verifier_id must be non-empty")
        if p_norm.lower() == v_norm.lower():
            raise SelfAttestationError(f"self-attestation rejected: proposer_id == verifier_id ({p_norm})")
        if not claim_digest.startswith("sha256:") or len(claim_digest) != 71:
            raise ValueError("claim_digest must be a canonical 64-hex sha256:<hex> string")
        seq = len(self._records)
        prev = self.head_sha256
        rec_sha = _canonical_record_sha256(seq, p_norm, v_norm, claim_digest, verdict, prev)
        rec = OutOfBandRecord(
            seq=seq,
            proposer_id=p_norm,
            verifier_id=v_norm,
            claim_digest=claim_digest,
            verdict=verdict,
            prev_sha256=prev,
            record_sha256=rec_sha,
        )
        self._records.append(rec)
        return rec

    @staticmethod
    def verify_records(records: list[OutOfBandRecord] | tuple[OutOfBandRecord, ...]) -> tuple[bool, list[str]]:
        """Independently re-verify every link, identity separation, and SHA-256 digest."""
        errors: list[str] = []
        expected_prev = GENESIS_DIGEST
        for idx, rec in enumerate(records):
            if rec.seq != idx:
                errors.append(f"seq mismatch at {idx}: got {rec.seq}")
            if not rec.proposer_id.strip() or not rec.verifier_id.strip():
                errors.append(f"empty identity at seq {idx}")
            if rec.proposer_id.strip().lower() == rec.verifier_id.strip().lower():
                errors.append(f"self-attestation violation at seq {idx}: {rec.proposer_id}")
            if rec.prev_sha256 != expected_prev:
                errors.append(f"broken chain link at seq {idx}")
            expected_sha = _canonical_record_sha256(
                rec.seq,
                rec.proposer_id,
                rec.verifier_id,
                rec.claim_digest,
                rec.verdict,
                rec.prev_sha256,
            )
            if rec.record_sha256 != expected_sha:
                errors.append(f"tampered record digest at seq {idx}")
            expected_prev = rec.record_sha256
        return len(errors) == 0, errors


def verify_binary_chain_32(steps: int = 32) -> dict[str, Any]:
    """Compute the canonical 32-step binary FIPS 180-4 SHA-256 chain (Wave 66C parity)."""
    h = [0] * 8
    for idx in range(steps):
        proposer_id = 100 + (idx % 7)
        verifier_id = 200 + (idx % 5)
        if proposer_id == verifier_id:
            raise SelfAttestationError("binary chain proposer_id collided with verifier_id")
        rec = struct.pack(">8I", h[0], h[1], h[2], h[3], idx, proposer_id, verifier_id, 7)
        h = list(struct.unpack(">8I", hashlib.sha256(rec).digest()))
    digest = "sha256:" + "".join(f"{w:08x}" for w in h)
    return {"schema": "n49-binary-sha256-chain/1", "steps": steps, "chain_sha": digest}
