"""AES-256-GCM provider for macOS and Linux, behind the `encryption` extra.

The master key lives in the OS keychain (`security` on macOS, `secret-tool`
on Linux), passed on stdin and never on a command line. Each item is
encrypted under HMAC-SHA256(master, item key), with a random 12-byte nonce
and the file header as associated data. `cryptography` is imported inside
functions, so no console script breaks when the extra is not installed.

Keychain access has no CI coverage; it is a manual check, and when the
keychain or the extra is missing the caller falls back to plaintext and says
so. Tests use the same provider with a key held in memory.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import subprocess
import sys

from .trace_enc import EncError

SERVICE = "flywheel-trace-custody"
_NONCE = 12


class AeadProvider:
    name = "aes-256-gcm"

    def __init__(self, master_key) -> None:
        self._master_key = master_key  # a callable returning 32 bytes

    def _gcm(self, key: bytes):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key)

    def _item_key(self, key: bytes) -> bytes:
        return hmac.new(self._master_key(), b"flywheel.item.v1\0" + key,
                        hashlib.sha256).digest()

    def _box(self, key: bytes, data: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE)
        return nonce + self._gcm(key).encrypt(nonce, data, aad)

    def _open(self, key: bytes, blob: bytes, aad: bytes) -> bytes:
        from cryptography.exceptions import InvalidTag
        try:
            return self._gcm(key).decrypt(blob[:_NONCE], blob[_NONCE:], aad)
        except (InvalidTag, ValueError):
            raise EncError("ENC_INTEGRITY") from None

    def encrypt(self, key, plaintext, aad):
        return self._box(self._item_key(key), plaintext, aad)

    def decrypt(self, key, blob, aad):
        return self._open(self._item_key(key), blob, aad)

    def seal(self, data, context):
        return self._box(self._master_key(), data, context)

    def unseal(self, blob, context):
        return self._open(self._master_key(), blob, context)

    def status(self) -> dict:
        return {"provider": self.name, "available": True,
                "protection": "encrypted (aes-256-gcm, keychain key)"}


def _run(argv, stdin: bytes | None = None) -> bytes | None:
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _keychain_get() -> bytes | None:
    if sys.platform == "darwin":
        out = _run(["security", "find-generic-password", "-s", SERVICE, "-a", "custody", "-w"])
    else:
        out = _run(["secret-tool", "lookup", "service", SERVICE, "account", "custody"])
    try:
        key = bytes.fromhex(out.decode().strip()) if out else None
    except (UnicodeError, ValueError):
        return None
    return key if key and len(key) == 32 else None


def _keychain_create() -> bytes | None:
    secret = os.urandom(32).hex().encode()
    if sys.platform == "darwin":
        # -w with no value reads the password from stdin, twice (entry and confirm).
        _run(["security", "add-generic-password", "-s", SERVICE, "-a", "custody", "-w"],
             secret + b"\n" + secret + b"\n")
    else:
        _run(["secret-tool", "store", "--label=Flywheel trace custody", "service", SERVICE,
              "account", "custody"], secret)
    return _keychain_get()


def keychain_provider():
    """An AES-GCM provider with a keychain key, or None when the extra or the
    keychain tool is missing."""
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
    except ImportError:
        return None
    if not shutil.which("security" if sys.platform == "darwin" else "secret-tool"):
        return None
    cache: list[bytes] = []

    def master() -> bytes:
        if not cache:
            key = _keychain_get() or _keychain_create()
            if key is None:
                raise EncError("OS_KEY_UNAVAILABLE")
            cache.append(key)
        return cache[0]
    return AeadProvider(master)
