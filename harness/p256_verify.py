"""p256_verify.py -- ECDSA P-256 with SHA-256 verification, stdlib only, verify only.

Sigstore's Rekor signs its signed entry timestamps and its checkpoints with an
ECDSA P-256 key. A stranger who rechecks a Rekor anchor offline has to verify
those signatures, and the offline promise is that they need nothing installed.
So this is the smallest ECDSA verifier that does the job: FIPS 186-4 section
6.4.2, affine arithmetic with modular inverses, written to be read.

VERIFY ONLY, for the same reason as `ed25519_verify`: a verifier needs nothing
from the stranger, and a signer belongs in audited tooling. Performance is not a
goal; one verification takes milliseconds.

Inputs it refuses rather than guesses at: a public key that is not on the curve,
an r or s outside [1, n-1], and a DER signature with trailing bytes or a
non-minimal integer. The last two are malleability: two byte strings for one
signature break anything that treats a signature as an identifier.
"""
from __future__ import annotations

import base64
import hashlib

# NIST P-256 (secp256r1), FIPS 186-4 appendix D.1.2.3.
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

# The DER prefix of a SubjectPublicKeyInfo for an uncompressed P-256 point:
# SEQUENCE { SEQUENCE { id-ecPublicKey, prime256v1 }, BIT STRING 0x00 0x04 ... }
_SPKI_PREFIX = bytes.fromhex(
    "3059301306072a8648ce3d020106082a8648ce3d030107034200")


class P256Error(ValueError):
    """A malformed key or signature encoding, as distinct from a bad signature."""


def _on_curve(pt) -> bool:
    x, y = pt
    return (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _mul(pt, k: int):
    acc = None
    while k:
        if k & 1:
            acc = _add(acc, pt)
        pt = _add(pt, pt)
        k >>= 1
    return acc


def pem_to_der(pem: str | bytes) -> bytes:
    """The DER bytes inside a single PEM block."""
    text = pem.decode("ascii") if isinstance(pem, (bytes, bytearray)) else pem
    lines = [ln.strip() for ln in text.strip().splitlines()]
    if not lines or not lines[0].startswith("-----BEGIN") or not lines[-1].startswith("-----END"):
        raise P256Error("not a PEM block")
    return base64.b64decode("".join(lines[1:-1]), validate=True)


def public_key_from_spki(der: bytes) -> tuple[int, int]:
    """The curve point inside a P-256 SubjectPublicKeyInfo, checked on the curve."""
    der = bytes(der)
    if len(der) != len(_SPKI_PREFIX) + 65 or not der.startswith(_SPKI_PREFIX):
        raise P256Error("not an uncompressed P-256 SubjectPublicKeyInfo")
    point = der[len(_SPKI_PREFIX):]
    if point[0] != 4:
        raise P256Error("only uncompressed points are accepted")
    pt = (int.from_bytes(point[1:33], "big"), int.from_bytes(point[33:], "big"))
    if not (pt[0] < P and pt[1] < P and _on_curve(pt)):
        raise P256Error("public key is not on P-256")
    return pt


def _der_int(buf: bytes, i: int) -> tuple[int, int]:
    if i + 2 > len(buf) or buf[i] != 0x02:
        raise P256Error("expected a DER INTEGER")
    n = buf[i + 1]
    body = buf[i + 2:i + 2 + n]
    if n == 0 or n > 33 or len(body) != n:
        raise P256Error("bad DER INTEGER length")
    if body[0] & 0x80 or (n > 1 and body[0] == 0 and not body[1] & 0x80):
        raise P256Error("non-minimal or negative DER INTEGER")
    return int.from_bytes(body, "big"), i + 2 + n


def decode_der_signature(sig: bytes) -> tuple[int, int]:
    """(r, s) from a DER ECDSA-Sig-Value, refusing any non-canonical encoding."""
    sig = bytes(sig)
    if len(sig) < 8 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise P256Error("not a DER ECDSA signature")
    r, i = _der_int(sig, 2)
    s, i = _der_int(sig, i)
    if i != len(sig):
        raise P256Error("trailing bytes after the DER signature")
    return r, s


def verify_digest(public_key: tuple[int, int], digest: bytes, sig_der: bytes) -> bool:
    """True iff `sig_der` is a valid ECDSA signature over the SHA-256 `digest`.

    Raises P256Error for a malformed signature encoding. Returns False for a well
    formed signature that does not verify.
    """
    r, s = decode_der_signature(sig_der)
    if not (1 <= r < N and 1 <= s < N):
        return False
    e = int.from_bytes(bytes(digest)[:32], "big")
    w = pow(s, -1, N)
    pt = _add(_mul(G, e * w % N), _mul(public_key, r * w % N))
    return pt is not None and pt[0] % N == r


def verify(public_key: tuple[int, int], message: bytes, sig_der: bytes) -> bool:
    """True iff `sig_der` is a valid ECDSA P-256 SHA-256 signature over `message`."""
    return verify_digest(public_key, hashlib.sha256(bytes(message)).digest(), sig_der)
