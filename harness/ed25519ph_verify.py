"""ed25519ph_verify.py -- RFC 8032 Ed25519ph verification, stdlib only, verify only.

Ed25519ph signs SHA-512(message) under the domain prefix dom2(1, ""), with an
empty context (RFC 8032 section 5.1). It is the form Sigstore's Rekor checks for
an Ed25519 key in a `hashedrekord` entry, because Rekor only ever sees the
digest. Same key and curve as plain Ed25519; only the hashed input differs, so a
plain Ed25519 signature never verifies here and an Ed25519ph signature never
verifies in `ed25519_verify.verify`.

The curve arithmetic is `ed25519_verify`'s, reused unchanged: that module is a
reviewed, hash-pinned file, so the prehashed variant lives beside it rather than
inside it. The malleability and off-curve rules are the same.
"""
from __future__ import annotations

import hashlib

from .ed25519_verify import (B, KEY_LEN, L, SIG_LEN, Ed25519Error, _add, _equal,
                             _scalarmult, decode_point, is_canonical_scalar)

# dom2(phflag=1, context=""): the prefix that separates Ed25519ph from Ed25519.
DOM2_PH = b"SigEd25519 no Ed25519 collisions" + bytes([1, 0])


def verify_ph(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True iff `signature` is a valid Ed25519ph signature over `message`.

    Raises Ed25519Error for malformed inputs. Returns False for a well formed
    signature that does not verify.
    """
    for name, value, length in (("public key", public_key, KEY_LEN),
                                ("signature", signature, SIG_LEN)):
        if not isinstance(value, (bytes, bytearray)) or len(value) != length:
            raise Ed25519Error(f"{name} must be {length} bytes")
    if not isinstance(message, (bytes, bytearray)):
        raise Ed25519Error("message must be bytes")
    r_enc, s_enc = bytes(signature[:32]), bytes(signature[32:])
    if not is_canonical_scalar(s_enc):
        return False
    a_point = decode_point(bytes(public_key))
    try:
        r_point = decode_point(r_enc)
    except Ed25519Error:
        return False
    prehash = hashlib.sha512(bytes(message)).digest()
    s = int.from_bytes(s_enc, "little")
    k = int.from_bytes(hashlib.sha512(
        DOM2_PH + r_enc + bytes(public_key) + prehash).digest(), "little") % L
    lhs = _scalarmult(B, (8 * s) % (8 * L))
    rhs = _add(_scalarmult(r_point, 8), _scalarmult(a_point, (8 * k) % (8 * L)))
    return _equal(lhs, rhs)
