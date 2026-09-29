"""Encryption at rest for trace custody: format, errors, providers (7.3, I7).

A custody file is either canonical JSON (first byte `{`) or
`FWENC1\\n` + one canonical JSON header line + `\\n` + ciphertext. The header
(`alg`, `bucket`, `file`, `item`, `v`) is authenticated: it is the AEAD
associated data, and the DPAPI provider binds its digest inside the
plaintext. Inside the ciphertext: a 4-byte length, the payload, and zero
padding to a size bucket (1 KiB, powers of two to 64 KiB, then multiples of
64 KiB), so short records do not reveal their length. A reader requires the
header's item and file to be the ones it asked for (ENC_BINDING).

Providers are injected. `default_provider()` picks DPAPI on Windows, AES-GCM
with a keychain key elsewhere when the `encryption` extra is installed, and
otherwise `NoProvider`, which is plaintext and says so on every status call.
No key stored beside the data is described as encryption.
"""
from __future__ import annotations

import json
import struct
import sys
import threading

from .evidence_json import canonical_bytes

MAGIC = b"FWENC1\n"
VERSION = 1
_KIB = 1024
_LOCK = threading.Lock()
_OVERRIDE = []


class EncError(Exception):
    """ENC_INTEGRITY, ENC_BINDING, ENC_FORMAT, ENC_REQUIRED, ENC_DOWNGRADE,
    KEY_DESTROYED, OS_KEY_UNAVAILABLE, ENC_UNAVAILABLE or ENC_UNREADABLE:<code>."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NoProvider:
    """No usable OS key store: plaintext, stated wherever protection is shown."""
    name = "none"

    def __init__(self, reason: str = "no OS key store") -> None:
        self.reason = reason

    def encrypt(self, key, plaintext, aad):
        raise EncError("ENC_UNAVAILABLE")

    decrypt = seal = unseal = encrypt

    def status(self) -> dict:
        return {"provider": self.name, "available": False,
                "protection": f"plaintext ({self.reason})"}


def bucket_size(n: int) -> int:
    if n <= _KIB:
        return _KIB
    if n <= 64 * _KIB:
        size = _KIB
        while size < n:
            size *= 2
        return size
    return -(-n // (64 * _KIB)) * 64 * _KIB


def pad(payload: bytes) -> bytes:
    inner = struct.pack(">I", len(payload)) + payload
    return inner + b"\0" * (bucket_size(len(inner)) - len(inner))


def unpad(inner: bytes) -> bytes:
    if len(inner) < 4:
        raise EncError("ENC_INTEGRITY")
    length = struct.unpack(">I", inner[:4])[0]
    if 4 + length > len(inner) or inner[4 + length:].strip(b"\0"):
        raise EncError("ENC_INTEGRITY")
    return inner[4:4 + length]


def overhead(n: int) -> int:
    """An upper bound on file bytes for a plaintext of `n` bytes."""
    return bucket_size(n + 4) + 4 * _KIB


def encode(provider, key: bytes, item: str, file: str, plaintext: bytes) -> bytes:
    inner = pad(plaintext)
    header = canonical_bytes({"alg": provider.name, "bucket": len(inner), "file": file,
                              "item": item, "v": VERSION})
    return MAGIC + header + b"\n" + provider.encrypt(key, inner, MAGIC + header)


def parse(blob: bytes) -> tuple[dict, bytes, bytes]:
    if not blob.startswith(MAGIC):
        raise EncError("ENC_FORMAT")
    end = blob.find(b"\n", len(MAGIC))
    if end < 0 or end - len(MAGIC) > 1024:
        raise EncError("ENC_FORMAT")
    header_bytes = blob[len(MAGIC):end]
    try:
        header = json.loads(header_bytes)
    except ValueError:
        raise EncError("ENC_INTEGRITY") from None
    if type(header) is not dict or set(header) != {"alg", "bucket", "file", "item", "v"}:
        raise EncError("ENC_INTEGRITY")
    return header, header_bytes, blob[end + 1:]


def decode(provider, key_for, item: str, file: str, blob: bytes) -> bytes:
    """`key_for(item)` returns the item key or None when it was destroyed."""
    header, header_bytes, body = parse(blob)
    if header["item"] != item or header["file"] != file:
        raise EncError("ENC_BINDING")
    if header["v"] != VERSION or header["alg"] != provider.name:
        raise EncError(f"ENC_UNREADABLE:{str(header['alg'])[:24]}")
    key = key_for(item)
    if key is None:
        raise EncError("KEY_DESTROYED")
    inner = provider.decrypt(key, body, MAGIC + header_bytes)
    if len(inner) != header["bucket"]:
        raise EncError("ENC_INTEGRITY")
    return unpad(inner)


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def _detect():
    if sys.platform == "win32":
        from .trace_enc_dpapi import DpapiProvider
        return DpapiProvider()
    from .trace_enc_aead import keychain_provider
    return keychain_provider() or NoProvider()


_DETECTED = []


def default_provider():
    """The provider in effect: an override set by tests, else the detected
    one when its start-up probe passes, else plaintext naming the failure."""
    with _LOCK:
        if _OVERRIDE:
            return _OVERRIDE[-1]
        if not _DETECTED:
            from .trace_enc_probe import probe
            found = _detect()
            result = probe(found)
            _DETECTED.append(found if result["ok"] else
                             NoProvider(f"unavailable: {result['code']}"))
        return _DETECTED[0]


def set_default_provider(provider):
    """Install `provider` (or None to restore detection); returns the previous
    override. For tests and the probe; never read from the environment."""
    with _LOCK:
        previous = _OVERRIDE.pop() if _OVERRIDE else None
        if provider is not None:
            _OVERRIDE.append(provider)
        return previous
