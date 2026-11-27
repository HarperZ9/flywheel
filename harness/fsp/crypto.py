"""Signing, verification and the signed-message envelope.

Seats, logs, witnesses, time servers and landmarks sign with Ed25519 (RFC
8032). A device signs with whatever its hardware backend offers. The Windows
TPM backend offers ECDSA P-256 and no Ed25519, so verification accepts both
algorithms, each named in the signature record.

Signing uses `cryptography` when installed and falls back to `pynacl`.
Verification uses `cryptography` or `pynacl` for speed and falls back to
Flywheel's stdlib-only `harness.ed25519_verify` and `harness.p256_verify`
so offline verification requires zero third-party packages.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from harness import ed25519_verify, p256_verify

from .canon import canon, fingerprint, tag

ED25519 = "ed25519"
P256 = "ecdsa-p256-sha256"

try:
    from cryptography.exceptions import InvalidSignature as _CryptoInvalid
    from cryptography.hazmat.primitives import hashes as _chashes
    from cryptography.hazmat.primitives import serialization as _cser
    from cryptography.hazmat.primitives.asymmetric import ec as _cec
    from cryptography.hazmat.primitives.asymmetric import ed25519 as _ced25519
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature as _encode_dss

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

try:
    from nacl.exceptions import BadSignatureError as _NaclBadSig
    from nacl.signing import SigningKey as _NaclSigningKey
    from nacl.signing import VerifyKey as _NaclVerifyKey

    _HAS_PYNACL = True
except ImportError:
    _HAS_PYNACL = False


class Signer(Protocol):
    alg: str

    def public_hex(self) -> str: ...

    def sign(self, message: bytes) -> bytes: ...


class Ed25519Signer:
    alg = ED25519

    def __init__(self, key: Any | None = None) -> None:
        if key is not None:
            self._key = key
            self._backend = "cryptography" if _HAS_CRYPTOGRAPHY and hasattr(key, "public_key") else "pynacl"
            return
        if _HAS_CRYPTOGRAPHY:
            self._key = _ced25519.Ed25519PrivateKey.generate()
            self._backend = "cryptography"
        elif _HAS_PYNACL:
            self._key = _NaclSigningKey(os.urandom(32))
            self._backend = "pynacl"
        else:
            raise RuntimeError("Ed25519 signing requires 'cryptography' or 'pynacl'")

    @classmethod
    def from_seed(cls, seed32: bytes) -> Ed25519Signer:
        if len(seed32) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes")
        if _HAS_CRYPTOGRAPHY:
            return cls(_ced25519.Ed25519PrivateKey.from_private_bytes(seed32))
        if _HAS_PYNACL:
            return cls(_NaclSigningKey(seed32))
        raise RuntimeError("Ed25519 signing requires 'cryptography' or 'pynacl'")

    def public_hex(self) -> str:
        if self._backend == "cryptography":
            raw = self._key.public_key().public_bytes(_cser.Encoding.Raw, _cser.PublicFormat.Raw)
            return raw.hex()
        return bytes(self._key.verify_key).hex()

    def sign(self, message: bytes) -> bytes:
        if self._backend == "cryptography":
            return self._key.sign(message)
        return bytes(self._key.sign(message).signature)


def _der_uint(n: int) -> bytes:
    raw = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return bytes([0x02, len(raw)]) + raw


def _raw_rs_to_der(sig: bytes) -> bytes:
    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    if r == 0 or s == 0:
        raise ValueError("zero ECDSA component")
    body = _der_uint(r) + _der_uint(s)
    return bytes([0x30, len(body)]) + body


def verify_stdlib(alg: str, pub: bytes, message: bytes, sig: bytes) -> bool:
    """Pure Python stdlib verification backed by harness.ed25519_verify and harness.p256_verify."""
    if alg == ED25519:
        try:
            return ed25519_verify.verify(pub, message, sig)
        except ed25519_verify.Ed25519Error:
            return False
    if alg == P256:
        if len(sig) != 64 or len(pub) != 65 or pub[0] != 4:
            return False
        try:
            pt = (int.from_bytes(pub[1:33], "big"), int.from_bytes(pub[33:], "big"))
            if not (pt[0] < p256_verify.P and pt[1] < p256_verify.P and p256_verify._on_curve(pt)):
                return False
            return p256_verify.verify(pt, message, _raw_rs_to_der(sig))
        except (p256_verify.P256Error, ValueError):
            return False
    return False


def _verify_ed25519(pub: bytes, message: bytes, sig: bytes) -> bool:
    if _HAS_CRYPTOGRAPHY:
        try:
            _ced25519.Ed25519PublicKey.from_public_bytes(pub).verify(sig, message)
            return True
        except (_CryptoInvalid, ValueError):
            return False
    if _HAS_PYNACL:
        try:
            _NaclVerifyKey(pub).verify(message, sig)
            return True
        except (_NaclBadSig, ValueError, TypeError):
            return False
    return verify_stdlib(ED25519, pub, message, sig)


def _verify_p256(pub: bytes, message: bytes, sig: bytes) -> bool:
    if len(sig) != 64:
        return False
    if _HAS_CRYPTOGRAPHY:
        try:
            key = _cec.EllipticCurvePublicKey.from_encoded_point(_cec.SECP256R1(), pub)
            der = _encode_dss(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
            key.verify(der, message, _cec.ECDSA(_chashes.SHA256()))
            return True
        except (_CryptoInvalid, ValueError):
            return False
    return verify_stdlib(P256, pub, message, sig)


def verify(alg: str, pub_hex: str, message: bytes, sig_hex: str) -> bool:
    try:
        pub, sig = bytes.fromhex(pub_hex), bytes.fromhex(sig_hex)
    except (ValueError, TypeError):
        return False
    if alg == ED25519:
        return _verify_ed25519(pub, message, sig)
    if alg == P256:
        return _verify_p256(pub, message, sig)
    return False


def sign_record(signer: Signer, msg_type: str, body: Any) -> dict:
    """One attributable signature record over the tagged canonical body."""
    sig = signer.sign(tag(msg_type) + canon(body))
    return {"alg": signer.alg, "key": signer.public_hex(), "sig": sig.hex()}


def envelope(msg_type: str, body: dict, signers: list[Signer] | None = None) -> dict:
    """A signed message: type, body and a plain list of signatures."""
    msg = {"type": msg_type, "body": body, "sigs": []}
    for signer in signers or []:
        msg["sigs"].append(sign_record(signer, msg_type, body))
    return msg


def add_signature(msg: dict, signer: Signer) -> dict:
    msg["sigs"].append(sign_record(signer, msg["type"], msg["body"]))
    return msg


def valid_signers(msg: dict) -> list[str]:
    """Distinct keys whose signature verifies; one count per key (TUF rule)."""
    seen: list[str] = []
    message = tag(msg["type"]) + canon(msg["body"])
    for rec in msg.get("sigs", []):
        key = rec.get("key")
        if key in seen:
            continue
        if verify(rec.get("alg", ""), key or "", message, rec.get("sig", "")):
            seen.append(key)
    return seen


def signed_by(msg: dict, key_hex: str) -> bool:
    return key_hex in valid_signers(msg)


def msg_id(msg: dict) -> str:
    """Identifier of a message: fingerprint of its body without signatures."""
    return fingerprint(msg["type"], msg["body"])


def entry_bytes(msg: dict) -> bytes:
    """The bytes a log stores for a message, signatures included."""
    return canon(msg)
