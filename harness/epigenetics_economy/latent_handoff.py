# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""J12 Latent Idea-Space Handoff Channel: 48-Byte Orthogonal SHA-256 Codec.

Pure Python stdlib implementation bit-exact with BuildLang SIG-067:
  - 36-DOF spatial state projected through a deterministic Modified Gram-Schmidt
    36x36 orthonormal basis Q
  - 48-byte wire format: [4B IEEE-754 f32 scale LE | 36B int8 z | 8B SHA-256 tag]
  - Fail-closed integrity check rejecting any 1-bit packet corruption.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence


class LatentChecksumError(ValueError):
    """Raised fail-closed when a 48-byte latent packet fails SHA-256 verification."""


def build_orthonormal_basis(dim: int = 36) -> list[list[float]]:
    """Construct deterministic diagonally dominant full-rank orthonormal basis via MGS."""
    q: list[list[float]] = []
    for r in range(dim):
        row: list[float] = []
        for c in range(dim):
            val = math.sin(float(r * 17 + c * 31 + r * c * 7 + 13) * 0.37123) + 0.5 * math.cos(
                float(r * 29 - c * 13 + r * c * 5 + 7) * 0.21947
            )
            if r == c:
                val += 3.0
            row.append(val)
        q.append(row)

    for r in range(dim):
        for p in range(r):
            dot = sum(q[r][c] * q[p][c] for c in range(dim))
            for c in range(dim):
                q[r][c] -= dot * q[p][c]
        inv_norm = 1.0 / math.sqrt(sum(v * v for v in q[r]))
        for c in range(dim):
            q[r][c] *= inv_norm
    return q


def _round_half_away_zero(x: float) -> int:
    return int(x + 0.5) if x >= 0.0 else -int((-x) + 0.5)


def encode_latent_packet(state: Sequence[float], q_basis: Sequence[Sequence[float]]) -> bytes:
    """Encode 36-DOF continuous state into a 48-byte SHA-256 sealed latent packet."""
    n = len(q_basis)
    if len(state) != n:
        raise ValueError(f"STATE_DIM_MISMATCH:{len(state)}!={n}")
    z = [sum(q_basis[r][c] * float(state[c]) for c in range(n)) for r in range(n)]
    amax = max(1.0e-6, max(abs(v) for v in z))
    scale = amax / 127.0
    inv_scale = 1.0 / scale
    q_bytes = bytearray(n)
    for r, v in enumerate(z):
        qi = max(-127, min(127, _round_half_away_zero(v * inv_scale)))
        q_bytes[r] = qi & 0xFF
    payload = struct.pack("<f", scale) + bytes(q_bytes)
    tag8 = hashlib.sha256(payload).digest()[:8]
    return payload + tag8


def decode_latent_packet(packet: bytes, q_basis: Sequence[Sequence[float]]) -> list[float]:
    """Verify 8-byte FIPS 180-4 SHA-256 tag fail-closed and reconstruct spatial coordinates."""
    n = len(q_basis)
    expected_len = 4 + n + 8
    if len(packet) != expected_len:
        raise LatentChecksumError(f"INVALID_PACKET_LEN:{len(packet)}")
    payload = packet[: 4 + n]
    tag8 = packet[4 + n :]
    if hashlib.sha256(payload).digest()[:8] != tag8:
        raise LatentChecksumError("LATENT_SHA256_MISMATCH")
    scale = float(struct.unpack("<f", payload[:4])[0])
    z_hat = [((b - 256) if b >= 128 else b) * scale for b in payload[4:]]
    return [sum(q_basis[r][c] * z_hat[r] for r in range(n)) for c in range(n)]
