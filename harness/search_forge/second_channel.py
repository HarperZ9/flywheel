# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N27 Mandatory Typed Orthogonal Second-Channel Evidence Enforcer.

Requires every high-stakes claim to carry an independent second-channel witness
from a distinct typed modality (e.g. build_oracle vs static_ast, hardware_sensor
vs cryptographic_receipt) observed at or after the primary event timestamp.
Rejects empty channels, same-channel corroboration, unknown types, causal-reversed
timestamps, and tampered envelope digests fail-closed. Pure stdlib Python only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

ChannelKind = str

VALID_CHANNEL_KINDS: frozenset[str] = frozenset(
    {
        "build_oracle",
        "static_ast",
        "cryptographic_receipt",
        "hardware_sensor",
        "visual_render_diff",
        "differential_reference",
        "out_of_band_corpus",
    }
)


@dataclass(frozen=True)
class SecondChannelEnvelope:
    """Typed orthogonal corroboration envelope binding primary and second channels."""

    claim_sha256: str
    primary_channel: ChannelKind
    primary_timestamp_ns: int
    second_channel: ChannelKind
    second_timestamp_ns: int
    second_witness_sha256: str
    envelope_sha256: str


@dataclass(frozen=True)
class SecondChannelVerdict:
    """Fail-closed verdict for a SecondChannelEnvelope."""

    ok: bool
    verdict: str
    errors: tuple[str, ...]


def _is_canonical_sha256(val: str) -> bool:
    if not val.startswith("sha256:") or len(val) != 71:
        return False
    hex_part = val[7:]
    return all(ch in "0123456789abcdef" for ch in hex_part)


def _compute_envelope_sha256(
    claim_sha256: str,
    primary_channel: str,
    primary_timestamp_ns: int,
    second_channel: str,
    second_timestamp_ns: int,
    second_witness_sha256: str,
) -> str:
    body = json.dumps(
        {
            "claim_sha256": claim_sha256,
            "primary_channel": primary_channel,
            "primary_timestamp_ns": primary_timestamp_ns,
            "second_channel": second_channel,
            "second_timestamp_ns": second_timestamp_ns,
            "second_witness_sha256": second_witness_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def build_second_channel_envelope(
    claim_sha256: str,
    primary_channel: ChannelKind,
    primary_timestamp_ns: int,
    second_channel: ChannelKind,
    second_timestamp_ns: int,
    second_witness_sha256: str,
) -> SecondChannelEnvelope:
    """Build and SHA-256 seal a SecondChannelEnvelope (caller verifies via verify_second_channel)."""
    p_norm = primary_channel.strip().lower()
    s_norm = second_channel.strip().lower()
    env_sha = _compute_envelope_sha256(
        claim_sha256,
        p_norm,
        primary_timestamp_ns,
        s_norm,
        second_timestamp_ns,
        second_witness_sha256,
    )
    return SecondChannelEnvelope(
        claim_sha256=claim_sha256,
        primary_channel=p_norm,
        primary_timestamp_ns=primary_timestamp_ns,
        second_channel=s_norm,
        second_timestamp_ns=second_timestamp_ns,
        second_witness_sha256=second_witness_sha256,
        envelope_sha256=env_sha,
    )


def verify_second_channel(env: SecondChannelEnvelope) -> SecondChannelVerdict:
    """Enforce orthogonal channel typing, causal ordering, and SHA-256 envelope integrity."""
    errors: list[str] = []
    if not _is_canonical_sha256(env.claim_sha256):
        errors.append("invalid_claim_sha256")
    if not _is_canonical_sha256(env.second_witness_sha256):
        errors.append("invalid_second_witness_sha256")
    if not env.primary_channel or env.primary_channel not in VALID_CHANNEL_KINDS:
        errors.append(f"invalid_primary_channel:{env.primary_channel}")
    if not env.second_channel or env.second_channel not in VALID_CHANNEL_KINDS:
        errors.append(f"invalid_second_channel:{env.second_channel}")
    if env.primary_channel and env.primary_channel == env.second_channel:
        errors.append("same_channel_self_corroboration")
    if env.primary_timestamp_ns <= 0 or env.second_timestamp_ns <= 0:
        errors.append("non_positive_timestamp")
    if env.second_timestamp_ns < env.primary_timestamp_ns:
        errors.append("causal_reversal_second_before_primary")
    if env.second_witness_sha256 == env.claim_sha256 and _is_canonical_sha256(env.claim_sha256):
        errors.append("duplicate_witness_equals_claim_digest")
    expected_sha = _compute_envelope_sha256(
        env.claim_sha256,
        env.primary_channel,
        env.primary_timestamp_ns,
        env.second_channel,
        env.second_timestamp_ns,
        env.second_witness_sha256,
    )
    if env.envelope_sha256 != expected_sha:
        errors.append("envelope_sha256_tampered")
    ok = len(errors) == 0
    return SecondChannelVerdict(ok=ok, verdict="PASS" if ok else "REJECT", errors=tuple(errors))


def verify_channel_batch(envelopes: list[SecondChannelEnvelope]) -> dict[str, Any]:
    """Audit a batch of N27 envelopes fail-closed."""
    if not envelopes:
        return {"schema": "n27-second-channel/1", "ok": False, "verdict": "REJECT", "passed": 0, "total": 0}
    passed = 0
    failed_indices: list[int] = []
    for idx, env in enumerate(envelopes):
        if verify_second_channel(env).ok:
            passed += 1
        else:
            failed_indices.append(idx)
    ok = len(failed_indices) == 0
    return {
        "schema": "n27-second-channel/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "passed": passed,
        "total": len(envelopes),
        "failed_indices": failed_indices,
    }
