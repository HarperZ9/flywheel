"""Test-only encryption providers and fixture helpers.

`StreamTestProvider` is an HMAC-SHA256 keystream with an HMAC tag, standard
library only, so the format, keystore, prefix and tamper logic run on every
OS. It lives in tests on purpose: nothing Flywheel ships uses a homemade
cipher. `UnavailableProvider` behaves as DPAPI does when the owner's master
key is gone (a forced password reset, another machine).
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import random
import sqlite3
import string

from harness import trace_enc
from harness.trace_enc import EncError


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    out, counter = b"", 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


class StreamTestProvider:
    name = "test"

    def __init__(self, master: bytes | None = None) -> None:
        self.master = master or os.urandom(32)

    def _box(self, key: bytes, data: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(16)
        body = bytes(a ^ b for a, b in zip(data, _stream(key, nonce, len(data))))
        tag = hmac.new(key, b"tag" + nonce + aad + body, hashlib.sha256).digest()
        return nonce + body + tag

    def _open(self, key: bytes, blob: bytes, aad: bytes) -> bytes:
        nonce, body, tag = blob[:16], blob[16:-32], blob[-32:]
        want = hmac.new(key, b"tag" + nonce + aad + body, hashlib.sha256).digest()
        if len(blob) < 48 or not hmac.compare_digest(tag, want):
            raise EncError("ENC_INTEGRITY")
        return bytes(a ^ b for a, b in zip(body, _stream(key, nonce, len(body))))

    def encrypt(self, key, plaintext, aad):
        return self._box(key, plaintext, aad)

    def decrypt(self, key, blob, aad):
        return self._open(key, blob, aad)

    def seal(self, data, context):
        return self._box(self.master, data, context)

    def unseal(self, blob, context):
        return self._open(self.master, blob, context)

    def status(self):
        return {"provider": self.name, "protection": "encrypted (test)", "available": True}


class UnavailableProvider(StreamTestProvider):
    """Encrypts normally; every item decryption then fails as a lost OS key."""

    def decrypt(self, key, blob, aad):
        raise EncError("OS_KEY_UNAVAILABLE")


@contextlib.contextmanager
def using(provider):
    previous = trace_enc.set_default_provider(provider)
    try:
        yield provider
    finally:
        trace_enc.set_default_provider(previous)


def long_canary(seed: int = 7, size: int = 10 * 1024) -> str:
    """At least 10 KiB of random text with letters that differ between NFC and NFD."""
    rng = random.Random(seed)
    letters = string.ascii_letters + "éüñçåø"
    return "".join(rng.choice(letters + " ") for _ in range(size))


def shingles(text: str, width: int = 16, step: int = 997) -> list[bytes]:
    raw = text.encode("utf-8")
    return [raw[i:i + width] for i in range(0, len(raw) - width, step)]


def plain_delete(db, sql: str, params=()) -> None:
    """Run one DELETE with nothing set to clear the pages it frees, the
    precondition of every control that shows the residue a plain delete
    leaves. SQLite's secure_delete, which zeroes freed pages, is a build-time
    default: ON in the Debian and Ubuntu builds, OFF in python.org's Windows
    build. auto_vacuum, which moves freed pages to the end of the file and cuts
    them off, is one too. So this sets both off on the database and the
    connection instead of trusting the platform, and checks that they took."""
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA auto_vacuum=NONE")
        con.execute("VACUUM")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        assert con.execute("PRAGMA auto_vacuum").fetchone() == (0,)
        assert con.execute("PRAGMA secure_delete=OFF").fetchone() == (0,)
        con.execute(sql, params)
        con.commit()
    finally:
        con.close()
