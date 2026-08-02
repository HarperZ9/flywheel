"""signatures.py -- ed25519 asymmetric signature support for receipts.

Provides detached ed25519 signatures over canonical receipt bytes, enabling
non-repudiation and third-party verification without a shared secret.

Uses the `cryptography` library (available on Python 3.12+) as the primary
backend, with `pynacl` as a fallback. If neither is installed, the module
reports UNAVAILABLE and the hash-based receipt path works unchanged.

This is the encryption-based workflow path alongside the hash-based one:
  - Hash-based (existing): sha256 seal, offline-verifiable, no key needed
  - Signature-based (new): ed25519 detached signature, non-repudiable,
    requires the signer's public key to verify
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

# Detect which backend is available.
_BACKEND: str = "none"
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption)
    _BACKEND = "cryptography"
except ImportError:
    try:
        import nacl.signing
        import nacl.encoding
        _BACKEND = "pynacl"
    except ImportError:
        pass


def crypto_available() -> bool:
    """True if an asymmetric crypto backend is installed."""
    return _BACKEND != "none"


def backend_name() -> str:
    """Return the active crypto backend name."""
    return _BACKEND


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def generate_keypair() -> tuple[str, str]:
    """Generate an ed25519 keypair. Returns (private_key_pem, public_key_pem).

    Raises RuntimeError if no crypto backend is available.
    """
    if _BACKEND == "cryptography":
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        priv_pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
        pub_pem = public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        return priv_pem, pub_pem
    elif _BACKEND == "pynacl":
        signing_key = nacl.signing.SigningKey.generate()
        priv_pem = signing_key.encode(encoder=nacl.encoding.Base64Encoder).decode()
        pub_pem = signing_key.verify_key.encode(
            encoder=nacl.encoding.Base64Encoder).decode()
        return priv_pem, pub_pem
    else:
        raise RuntimeError("no crypto backend available (install cryptography or pynacl)")


def public_key_fingerprint(public_key_pem: str) -> str:
    """Return a short fingerprint (sha256:hex16) of a public key."""
    digest = hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def sign_receipt(receipt: dict[str, Any], private_key_pem: str) -> str:
    """Sign a receipt's canonical bytes with ed25519. Returns base64 signature.

    The signature is detached: it covers the canonical JSON of the receipt
    but is stored separately. The receipt itself is unchanged.
    """
    canonical = _canonical_bytes(receipt)
    if _BACKEND == "cryptography":
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        private_key = load_pem_private_key(
            private_key_pem.encode(), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("private key is not ed25519")
        sig = private_key.sign(canonical)
        return base64.b64encode(sig).decode("ascii")
    elif _BACKEND == "pynacl":
        signing_key = nacl.signing.SigningKey(
            private_key_pem.encode(), encoder=nacl.encoding.Base64Encoder)
        signed = signing_key.sign(canonical)
        return base64.b64encode(signed.signature).decode("ascii")
    else:
        raise RuntimeError("no crypto backend available")


def verify_signature(receipt: dict[str, Any], signature_b64: str,
                     public_key_pem: str) -> bool:
    """Verify a detached ed25519 signature over a receipt.

    Returns True if the signature is valid, False otherwise.
    """
    canonical = _canonical_bytes(receipt)
    sig_bytes = base64.b64decode(signature_b64)

    if _BACKEND == "cryptography":
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        try:
            public_key = load_pem_public_key(public_key_pem.encode())
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            public_key.verify(sig_bytes, canonical)
            return True
        except Exception:
            return False
    elif _BACKEND == "pynacl":
        try:
            verify_key = nacl.signing.VerifyKey(
                public_key_pem.encode(), encoder=nacl.encoding.Base64Encoder)
            verify_key.verify(canonical, sig_bytes)
            return True
        except Exception:
            return False
    else:
        raise RuntimeError("no crypto backend available")


# ---------------------------------------------------------------------------
# Signed receipt wrapper
# ---------------------------------------------------------------------------

SIGNED_SCHEMA = "flywheel.signed-receipt/v1"


def wrap_signed(inner_receipt: dict[str, Any], private_key_pem: str) -> dict[str, Any]:
    """Wrap any existing receipt with a detached ed25519 signature.

    Returns a flywheel.signed-receipt/v1 dict carrying the inner receipt and
    the detached signature. The inner receipt is unchanged.
    """
    signature = sign_receipt(inner_receipt, private_key_pem)
    # Extract the public key for verification
    if _BACKEND == "cryptography":
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key, Encoding, PublicFormat)
        priv = load_pem_private_key(private_key_pem.encode(), password=None)
        pub_pem = priv.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    elif _BACKEND == "pynacl":
        signing_key = nacl.signing.SigningKey(
            private_key_pem.encode(), encoder=nacl.encoding.Base64Encoder)
        pub_pem = signing_key.verify_key.encode(
            encoder=nacl.encoding.Base64Encoder).decode()
    else:
        raise RuntimeError("no crypto backend")

    return {
        "schema": SIGNED_SCHEMA,
        "inner_receipt": inner_receipt,
        "signature": {
            "algorithm": "ed25519",
            "value": signature,
            "public_key": pub_pem,
            "public_key_fingerprint": public_key_fingerprint(pub_pem),
        },
    }


def verify_signed(signed_receipt: dict[str, Any]) -> dict[str, Any]:
    """Verify a signed receipt wrapper.

    Returns {verdict, detail}. The inner receipt is verified against the
    detached signature using the embedded public key.
    """
    if not isinstance(signed_receipt, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "not an object"}
    if signed_receipt.get("schema") != SIGNED_SCHEMA:
        return {"verdict": "UNVERIFIABLE", "detail": "schema mismatch"}

    inner = signed_receipt.get("inner_receipt")
    sig_block = signed_receipt.get("signature")
    if not isinstance(inner, dict) or not isinstance(sig_block, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "missing inner_receipt or signature"}

    algorithm = sig_block.get("algorithm", "")
    if algorithm != "ed25519":
        return {"verdict": "UNVERIFIABLE", "detail": f"unsupported algorithm: {algorithm}"}

    signature = sig_block.get("value", "")
    public_key = sig_block.get("public_key", "")
    if not signature or not public_key:
        return {"verdict": "UNVERIFIABLE", "detail": "missing signature or public_key"}

    if not crypto_available():
        return {"verdict": "UNVERIFIABLE",
                "detail": "no crypto backend to verify signature"}

    valid = verify_signature(inner, signature, public_key)
    if valid:
        return {"verdict": "MATCH",
                "fingerprint": sig_block.get("public_key_fingerprint", "")}
    return {"verdict": "TAMPERED", "detail": "signature verification failed"}


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    """Canonical JSON bytes for signing (compact, sorted keys, UTF-8)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
