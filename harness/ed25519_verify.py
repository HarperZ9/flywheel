"""ed25519_verify.py -- RFC 8032 Ed25519 verification, stdlib only, verify only.

This is the module the stranger-reproducibility bar rests on. Clone the repo, run
the verifier, check a signature, with nothing installed. If this needed the
`cryptography` package the offline promise would be a promise about the stranger's
package manager rather than about the evidence.

VERIFY ONLY, and the asymmetry is deliberate. A verifier is a stranger who must
need nothing. A signer is the author, who already has tooling. Shipping a
pure-Python signer would also invite key generation with an unaudited RNG inside a
module whose entire value is being small enough for one person to read.

Curve: twisted Edwards, -x^2 + y^2 = 1 + d x^2 y^2 over GF(2^255 - 19).
Verification: accept iff [8][S]B == [8]R + [8][k]A, where k = SHA512(R || A || M)
reduced mod L. The cofactor-8 form is the RFC's own equation and it is what makes
this agree with other implementations on edge cases rather than only on the happy
path.

Two traps this handles that naive implementations miss:

  1. **Non-canonical S.** S must already be reduced mod L. An unreduced S yields a
     SECOND valid signature over the same message, which is malleability: two
     distinct byte strings both verifying breaks any system that treats a
     signature as an identifier, and a receipt ledger does exactly that.
  2. **Off-curve points.** A public key or R with no matching curve point RAISES
     rather than returning False, so a caller can tell a malformed key from a
     wrong signature. Collapsing those two into one answer is how "this receipt
     is invalid" gets confused with "this receipt is unreadable".

Performance is not a goal. Scalar multiplication is double-and-add, roughly
milliseconds per verification, which is irrelevant next to being auditable.
"""
from __future__ import annotations

import hashlib

# Field and group parameters, RFC 8032 section 5.1.
P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)                 # sqrt(-1) mod P

# The base point B.
BY = 4 * pow(5, P - 2, P) % P
SIG_LEN = 64
KEY_LEN = 32


class Ed25519Error(ValueError):
    """A malformed key, signature, or point encoding.

    Distinct from a verification failure: a bad signature returns False, while an
    input that is not a signature at all raises. A verifier that conflates them
    cannot tell an invalid receipt from an unreadable one.
    """


def _x_from_y(y: int) -> int:
    """Recover x from y on the curve, or raise if no such point exists."""
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * I % P
    if (x * x - xx) % P != 0:
        raise Ed25519Error("encoding does not correspond to a curve point")
    return x


# Base point, computed once. _x_from_y returns one of the two roots; the base
# point's canonical encoding carries sign bit 0, which means x is EVEN. Taking
# the wrong root silently yields -B, and every RFC vector then fails while all
# the internal arithmetic still looks self-consistent.
_BX = _x_from_y(BY)
if _BX & 1:
    _BX = P - _BX
B = (_BX % P, BY % P, 1, _BX * BY % P)      # extended coordinates (X, Y, Z, T)


def _add(p, q):
    """Extended twisted Edwards addition (RFC 8032 section 5.1.4)."""
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * t1 * t2 * D % P
    dd = 2 * z1 * z2 % P
    e, f, g, hh = b - a, dd - c, dd + c, b + a
    return (e * f % P, g * hh % P, f * g % P, e * hh % P)


def _double(p):
    return _add(p, p)


def _scalarmult(p, e: int):
    """Double-and-add. Not constant time, which is fine: there is no secret here.
    Verification operates entirely on public values."""
    if e == 0:
        return (0, 1, 1, 0)                 # neutral element
    q = _scalarmult(p, e >> 1)
    q = _double(q)
    if e & 1:
        q = _add(q, p)
    return q


def _equal(p, q) -> bool:
    """Projective equality: compare X1*Z2 == X2*Z1 and Y1*Z2 == Y2*Z1."""
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    if (x1 * z2 - x2 * z1) % P != 0:
        return False
    return (y1 * z2 - y2 * z1) % P == 0


def decode_point(enc: bytes):
    """Decode a 32-byte little-endian point encoding into extended coordinates.

    Raises on an encoding with no corresponding curve point, or a y outside the
    field. Does NOT raise for low-order points: the cofactor-8 verification
    equation handles those, and rejecting them here would diverge from RFC 8032.
    """
    if not isinstance(enc, (bytes, bytearray)) or len(enc) != KEY_LEN:
        raise Ed25519Error(f"a point encoding is {KEY_LEN} bytes")
    raw = int.from_bytes(enc, "little")
    y = raw & ((1 << 255) - 1)
    sign = raw >> 255
    if y >= P:
        raise Ed25519Error("non-canonical y: not reduced mod p")
    x = _x_from_y(y)
    if x & 1 != sign:
        x = P - x
    return (x % P, y % P, 1, x * y % P)


def is_canonical_scalar(s: bytes) -> bool:
    """True iff s is a little-endian integer already reduced mod L.

    An unreduced S is a malleable second encoding of the same signature. This is
    a separate public function because the property is worth asserting directly in
    tests rather than only observing through a verification failure.
    """
    if not isinstance(s, (bytes, bytearray)) or len(s) != 32:
        return False
    return int.from_bytes(s, "little") < L


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True iff `signature` is a valid Ed25519 signature over `message`.

    Raises Ed25519Error for malformed inputs. Returns False for a well formed
    signature that does not verify.
    """
    for name, value, length in (("public key", public_key, KEY_LEN),
                                ("signature", signature, SIG_LEN)):
        if not isinstance(value, (bytes, bytearray)):
            raise Ed25519Error(f"{name} must be bytes")
        if len(value) != length:
            raise Ed25519Error(
                f"{name} must be {length} bytes, got {len(value)}")
    if not isinstance(message, (bytes, bytearray)):
        raise Ed25519Error("message must be bytes")

    r_enc, s_enc = bytes(signature[:32]), bytes(signature[32:])
    if not is_canonical_scalar(s_enc):
        # Malleability: an unreduced S is a second byte string for the same
        # signature. Refuse it rather than accept two identifiers for one claim.
        return False

    a_point = decode_point(bytes(public_key))
    try:
        r_point = decode_point(r_enc)
    except Ed25519Error:
        # R is attacker-supplied. A garbage R is a bad signature, not a malformed
        # key, so this one is False rather than a raise.
        return False

    s = int.from_bytes(s_enc, "little")
    k = int.from_bytes(
        hashlib.sha512(r_enc + bytes(public_key) + bytes(message)).digest(),
        "little") % L

    # [8][S]B == [8]R + [8][k]A
    lhs = _scalarmult(B, (8 * s) % (8 * L))
    rhs = _add(_scalarmult(r_point, 8), _scalarmult(a_point, (8 * k) % (8 * L)))
    return _equal(lhs, rhs)
