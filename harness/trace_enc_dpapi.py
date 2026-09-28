"""DPAPI provider (Windows): current-user scope, the item key as entropy.

`CryptProtectData` has no associated data, so the plaintext starts with the
sha256 of the header, checked on decryption. DPAPI does not authenticate every
byte of its own blob (a flipped byte near the start of a blob was accepted by
`CryptUnprotectData` on the reference machine, with the plaintext unchanged),
so each blob also carries an HMAC-SHA256 under the item key over the header
and the blob, and any flipped byte fails as ENC_INTEGRITY.

Error mapping (experiment X8, in part). Modified data and a wrong item key
returned 13 (ERROR_INVALID_DATA), observed. The codes for a master key that
cannot be decrypted (a forced password reset, another machine, some remote
logons) were not observed here; the set below is from Microsoft's error
tables, not from a run, and anything else maps to ENC_UNREADABLE:<code>.
"""
from __future__ import annotations

import hashlib
import hmac

from .capture_hooks import protect
from .trace_enc import EncError

_INTEGRITY = {13, 0x80090005}          # ERROR_INVALID_DATA, NTE_BAD_DATA
_KEY_UNAVAILABLE = {2, 3, 1312, 0x8009000B, 0x8009000D, 0x80090016, 0x80090345}
_MAC = 32


def map_error(code: int) -> str:
    code = code & 0xFFFFFFFF if type(code) is int else -1
    if code in _INTEGRITY:
        return "ENC_INTEGRITY"
    if code in _KEY_UNAVAILABLE:
        return "OS_KEY_UNAVAILABLE"
    return f"ENC_UNREADABLE:{code}"


def _mac(key: bytes, aad: bytes, blob: bytes) -> bytes:
    return hmac.new(key, b"flywheel.dpapi.mac.v1\0" + aad + b"\0" + blob,
                    hashlib.sha256).digest()


class DpapiProvider:
    name = "dpapi"

    def _unprotect(self, blob: bytes, entropy: bytes) -> bytes:
        try:
            return protect.unprotect(blob, entropy)
        except OSError as exc:
            raise EncError(map_error(exc.errno if exc.errno is not None else -1)) from None

    def encrypt(self, key: bytes, plaintext: bytes, aad: bytes) -> bytes:
        blob = protect.protect(hashlib.sha256(aad).digest() + plaintext, key)
        return blob + _mac(key, aad, blob)

    def decrypt(self, key: bytes, blob: bytes, aad: bytes) -> bytes:
        body, tag = blob[:-_MAC], blob[-_MAC:]
        if len(blob) <= _MAC or not hmac.compare_digest(tag, _mac(key, aad, body)):
            raise EncError("ENC_INTEGRITY")
        inner = self._unprotect(body, key)
        if inner[:32] != hashlib.sha256(aad).digest():
            raise EncError("ENC_INTEGRITY")
        return inner[32:]

    def seal(self, data: bytes, context: bytes) -> bytes:
        return protect.protect(data, context)

    def unseal(self, blob: bytes, context: bytes) -> bytes:
        return self._unprotect(blob, context)

    def status(self) -> dict:
        return {"provider": self.name, "available": True, "protection": "encrypted (dpapi)"}
