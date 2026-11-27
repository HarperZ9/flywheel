# SPDX-License-Identifier: MIT
"""Pure-stdlib RFC 8439 ChaCha20-Poly1305 AEAD verification harness.

Implements RFC 8439 ChaCha20 stream encryption, Poly1305 one-time MAC,
authenticated sealing/opening with constant-time tag comparison, and
JSON envelope validation for deterministic cryptographic attestation.
"""

from __future__ import annotations

import hmac
import struct
from collections.abc import Mapping

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib RFC 8439 ChaCha20-Poly1305 reference and attestation "
    "harness using hmac.compare_digest for tag verification. Python arbitrary-"
    "precision integers are not hardened against microarchitectural timing "
    "side-channels; use vetted native crypto libraries for production secret "
    "handling."
)

KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
ENVELOPE_SCHEMA = "flywheel-aead-envelope/1"
ENVELOPE_ALG = "chacha20-poly1305-rfc8439"
RFC8439_SECTION_2_8_2_TAG_HEX = "1ae10b594f09e26a7e902ecbd0600691"

_CHACHA_CONSTANTS = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)
_POLY1305_PRIME = (1 << 130) - 5
_POLY1305_CLAMP = 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
_MASK32 = 0xFFFFFFFF
_MASK128 = (1 << 128) - 1


class AeadAuthError(ValueError):
    """Raised fail-closed when AEAD authentication or framing fails."""


def _rotl32(value: int, shift: int) -> int:
    return ((value << shift) & _MASK32) | (value >> (32 - shift))


def _quarter_round(st: list[int], ia: int, ib: int, ic: int, id_: int) -> None:
    a, b, c, d = st[ia], st[ib], st[ic], st[id_]
    a = (a + b) & _MASK32
    d = _rotl32(d ^ a, 16)
    c = (c + d) & _MASK32
    b = _rotl32(b ^ c, 12)
    a = (a + b) & _MASK32
    d = _rotl32(d ^ a, 8)
    c = (c + d) & _MASK32
    b = _rotl32(b ^ c, 7)
    st[ia], st[ib], st[ic], st[id_] = a, b, c, d


def _require_bytes(value: object, expected_len: int, name: str) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != expected_len:
        raise AeadAuthError(f"{name} must be exactly {expected_len} bytes")
    return bytes(value)


def chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    """Compute one 64-byte RFC 8439 ChaCha20 keystream block."""
    key_b = _require_bytes(key, KEY_BYTES, "key")
    nonce_b = _require_bytes(nonce, NONCE_BYTES, "nonce")
    if not isinstance(counter, int) or counter < 0 or counter > _MASK32:
        raise AeadAuthError("counter must be an unsigned 32-bit integer")

    init = [
        *_CHACHA_CONSTANTS,
        *struct.unpack("<8I", key_b),
        counter,
        *struct.unpack("<3I", nonce_b),
    ]
    st = list(init)
    for _ in range(10):
        _quarter_round(st, 0, 4, 8, 12)
        _quarter_round(st, 1, 5, 9, 13)
        _quarter_round(st, 2, 6, 10, 14)
        _quarter_round(st, 3, 7, 11, 15)
        _quarter_round(st, 0, 5, 10, 15)
        _quarter_round(st, 1, 6, 11, 12)
        _quarter_round(st, 2, 7, 8, 13)
        _quarter_round(st, 3, 4, 9, 14)
    words = [(st[i] + init[i]) & _MASK32 for i in range(16)]
    return struct.pack("<16I", *words)


def chacha20_xor(key: bytes, counter: int, nonce: bytes, data: bytes) -> bytes:
    """XOR data with the RFC 8439 ChaCha20 keystream starting at counter."""
    if not isinstance(data, (bytes, bytearray)):
        raise AeadAuthError("data must be bytes")
    raw = bytes(data)
    if not raw:
        _require_bytes(key, KEY_BYTES, "key")
        _require_bytes(nonce, NONCE_BYTES, "nonce")
        return b""

    out = bytearray(len(raw))
    block_count = (len(raw) + 63) // 64
    if counter < 0 or counter + block_count - 1 > _MASK32:
        raise AeadAuthError("ChaCha20 32-bit block counter overflow")
    for idx in range(block_count):
        ks = chacha20_block(key, counter + idx, nonce)
        start = idx * 64
        chunk = raw[start : start + 64]
        for j, byte in enumerate(chunk):
            out[start + j] = byte ^ ks[j]
    return bytes(out)


def poly1305_mac(one_time_key: bytes, data: bytes) -> bytes:
    """Compute a 16-byte RFC 8439 Poly1305 authentication tag."""
    otk = _require_bytes(one_time_key, KEY_BYTES, "one_time_key")
    if not isinstance(data, (bytes, bytearray)):
        raise AeadAuthError("data must be bytes")
    msg = bytes(data)
    r = int.from_bytes(otk[:16], "little") & _POLY1305_CLAMP
    s = int.from_bytes(otk[16:32], "little")
    acc = 0
    for off in range(0, len(msg), 16):
        chunk = msg[off : off + 16]
        n = int.from_bytes(chunk + b"\x01", "little")
        acc = ((acc + n) * r) % _POLY1305_PRIME
    return ((acc + s) & _MASK128).to_bytes(TAG_BYTES, "little")


def _pad16(data: bytes) -> bytes:
    rem = len(data) % 16
    return b"" if rem == 0 else b"\x00" * (16 - rem)


def _compute_aead_tag(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    otk = chacha20_block(key, 0, nonce)[:32]
    mac_input = (
        aad
        + _pad16(aad)
        + ciphertext
        + _pad16(ciphertext)
        + struct.pack("<QQ", len(aad), len(ciphertext))
    )
    return poly1305_mac(otk, mac_input)


def aead_seal(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: bytes = b"",
) -> tuple[bytes, bytes]:
    """Encrypt and authenticate plaintext under RFC 8439 ChaCha20-Poly1305."""
    if not isinstance(plaintext, (bytes, bytearray)) or not isinstance(aad, (bytes, bytearray)):
        raise AeadAuthError("plaintext and aad must be bytes")
    pt = bytes(plaintext)
    aad_b = bytes(aad)
    ciphertext = chacha20_xor(key, 1, nonce, pt)
    tag = _compute_aead_tag(key, nonce, ciphertext, aad_b)
    return ciphertext, tag


def aead_open(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    tag: bytes,
    aad: bytes = b"",
) -> bytes:
    """Verify Poly1305 tag in constant time before decrypting ciphertext."""
    tag_b = _require_bytes(tag, TAG_BYTES, "tag")
    if not isinstance(ciphertext, (bytes, bytearray)) or not isinstance(aad, (bytes, bytearray)):
        raise AeadAuthError("ciphertext and aad must be bytes")
    ct = bytes(ciphertext)
    aad_b = bytes(aad)
    expected_tag = _compute_aead_tag(key, nonce, ct, aad_b)
    if not hmac.compare_digest(expected_tag, tag_b):
        raise AeadAuthError("RFC 8439 Poly1305 authentication tag mismatch")
    return chacha20_xor(key, 1, nonce, ct)


def seal_envelope(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: bytes = b"",
) -> dict[str, str]:
    """Seal plaintext and AAD into a versioned hex JSON envelope."""
    ct, tag = aead_seal(key, nonce, plaintext, aad=aad)
    return {
        "schema": ENVELOPE_SCHEMA,
        "alg": ENVELOPE_ALG,
        "nonce_hex": bytes(nonce).hex(),
        "aad_hex": bytes(aad).hex(),
        "ciphertext_hex": ct.hex(),
        "tag_hex": tag.hex(),
    }


def open_envelope(key: bytes, envelope: Mapping[str, object]) -> bytes:
    """Validate envelope framing and open payload fail-closed."""
    if not isinstance(envelope, Mapping):
        raise AeadAuthError("envelope must be a mapping")
    if envelope.get("schema") != ENVELOPE_SCHEMA or envelope.get("alg") != ENVELOPE_ALG:
        raise AeadAuthError("unsupported envelope schema or algorithm")
    try:
        nonce = bytes.fromhex(str(envelope["nonce_hex"]))
        aad = bytes.fromhex(str(envelope["aad_hex"]))
        ct = bytes.fromhex(str(envelope["ciphertext_hex"]))
        tag = bytes.fromhex(str(envelope["tag_hex"]))
    except (KeyError, ValueError) as exc:
        raise AeadAuthError(f"malformed envelope hex field: {exc}") from exc
    return aead_open(key, nonce, ct, tag, aad=aad)
