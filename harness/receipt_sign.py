"""receipt_sign.py -- attach a signature, and let a stranger check it.

The verification path here touches only `receipt`, `receipt_fields`, and
`ed25519_verify`, all stdlib-only. A person who distrusts the author can still
establish what the author's machine concluded, on a bare interpreter, offline.

Four disciplines:

1. THE SIGNATURE COVERS `claim_sha256`, per SIGNED_OVER fixed in receipt.py.
   Verification RECOMPUTES that digest from the receipt body rather than trusting
   the recorded one. A verifier that trusted the recorded digest would be
   verifying a signature over a number instead of over a claim, which is the
   difference between a receipt and a decoration.

2. A SIGNATURE MAY NOT DECLARE ITS OWN COVERAGE. `signed_over` travels in the
   envelope for a reader's benefit, but a mismatch against the code constant is a
   refusal. If a receipt could narrow its own coverage it would narrow it to
   nothing.

3. HMAC IS LOCAL ONLY. Verifying an HMAC requires the secret, and a stranger who
   holds the signing secret is not a third party. So HMAC signatures are marked
   non-exportable, refuse to verify against anything but their own secret, and are
   STRIPPED by `pack_for_export`, which adds the honest non-claim in their place.

4. AN ABSENT OR UNKNOWN ALGORITHM IS A NAMED REFUSAL, never a silent pass and
   never a bare False. "This receipt is unsigned" and "this signature is wrong"
   are different facts and a reader needs both.

This module does not generate keys and does not sign with Ed25519. `ed25519_attach`
takes a signature produced elsewhere. The asymmetry is deliberate: a verifier is a
stranger who must need nothing, a signer is the author who already has tooling, and
a pure-Python signer would invite key generation with an unaudited RNG.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
from dataclasses import dataclass, replace

from .ed25519_verify import verify as _ed_verify, Ed25519Error
from .receipt import LEGACY_SCHEMA, Receipt, SIGNED_OVER
from .receipt_fields import canonical

EXPORTABLE_ALGS = frozenset({"ed25519"})
LOCAL_ONLY_ALGS = frozenset({"hmac-sha256"})
KNOWN_ALGS = EXPORTABLE_ALGS | LOCAL_ONLY_ALGS


class SignError(ValueError):
    """A signature envelope that could not be built honestly."""


@dataclass
class SignedReceipt:
    receipt: Receipt
    sig_alg: str
    key_id: str
    sig_hex: str
    public_key_hex: str
    exportable: bool

    def to_dict(self) -> dict:
        return {
            "schema": "flywheel.signed-receipt/v1",
            "receipt": self.receipt.to_dict(),
            "signature": {
                "sig_alg": self.sig_alg,
                "key_id": self.key_id,
                "sig": self.sig_hex,
                "public_key": self.public_key_hex,
                "exportable": self.exportable,
                # Present for a reader; a mismatch against the code constant is a
                # refusal, so this can inform but never decide.
                "signed_over": list(SIGNED_OVER),
            },
        }


def unsigned(receipt: Receipt) -> dict:
    """A receipt with no signature. A legitimate state, and it says so."""
    return {"schema": "flywheel.signed-receipt/v1",
            "receipt": receipt.to_dict(), "signature": None}


def ed25519_attach(receipt: Receipt, signature: bytes, public_key: bytes, *,
                   key_id: str) -> SignedReceipt:
    """Attach an Ed25519 signature produced elsewhere over `claim_sha256`."""
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
        raise SignError("an ed25519 signature is 64 bytes")
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != 32:
        raise SignError("an ed25519 public key is 32 bytes")
    if not key_id:
        raise SignError("a signature needs a key_id so it can be rotated")
    return SignedReceipt(receipt=receipt, sig_alg="ed25519", key_id=key_id,
                         sig_hex=bytes(signature).hex(),
                         public_key_hex=bytes(public_key).hex(),
                         exportable=True)


def hmac_sign(receipt: Receipt, secret: bytes, *, key_id: str) -> SignedReceipt:
    """Local-only signature. Useful for detecting local tampering; useless to a
    third party, because checking it requires the secret. Marked accordingly."""
    if not isinstance(secret, (bytes, bytearray)) or not secret:
        raise SignError("an hmac secret must be non-empty bytes")
    tag = _hmac.new(bytes(secret), receipt.claim_sha256().encode(),
                    hashlib.sha256).hexdigest()
    return SignedReceipt(receipt=receipt, sig_alg="hmac-sha256", key_id=key_id,
                         sig_hex=tag, public_key_hex="", exportable=False)


def verify_signed(envelope: dict, public_key: bytes) -> tuple[bool, str]:
    """(ok, reason). Never raises on hostile input; a malformed envelope is a
    named refusal, because "unreadable" and "invalid" are different facts."""
    if not isinstance(envelope, dict):
        return False, "malformed_envelope"
    body = envelope.get("receipt")
    if not isinstance(body, dict) or not body:
        return False, "malformed_envelope"
    sig = envelope.get("signature")
    if sig is None:
        return False, "unsigned"
    if not isinstance(sig, dict) or not sig.get("sig_alg"):
        return False, "malformed_envelope"

    alg = sig["sig_alg"]
    if not isinstance(alg, str) or alg not in KNOWN_ALGS:
        # A json.loads'd sig_alg can be an unhashable list/dict; `x in frozenset`
        # would raise TypeError, escaping a verifier that promises a named refusal.
        return False, "unknown_algorithm"
    so = sig.get("signed_over", [])
    if not isinstance(so, (list, tuple)) or list(so) != list(SIGNED_OVER):
        # A non-iterable signed_over makes list() raise TypeError; name it instead.
        return False, "signed_over_mismatch"

    # Recompute the digest from the BODY. Trusting the recorded one would verify
    # a signature over a number rather than over a claim.
    try:
        recomputed = Receipt.from_dict(body).claim_sha256()
    except Exception:
        return False, "malformed_envelope"
    if recomputed != body.get("claim_sha256"):
        return False, "digest_mismatch"

    if alg in LOCAL_ONLY_ALGS:
        # A stranger cannot check this, and pretending otherwise would be the
        # exact overclaim the design forbids.
        return False, "local_only_algorithm"

    try:
        ok = _ed_verify(bytes(public_key), recomputed.encode(),
                        bytes.fromhex(sig["sig"]))
    except (Ed25519Error, ValueError, KeyError, TypeError):
        # A missing sig (KeyError) or a non-string sig (TypeError from fromhex)
        # are siblings of the ValueError a bad hex string raises: all a bad
        # signature, none a reason to crash the stranger running this offline.
        return False, "bad_signature"
    return (True, "ok") if ok else (False, "bad_signature")


def pack_for_export(envelope: dict) -> dict:
    """Prepare an envelope to leave this machine.

    A local-only signature is STRIPPED rather than shipped, and the honest
    non-claim goes in its place. Shipping an HMAC tag would invite a reader to
    treat it as verification when they cannot check it.
    """
    out = json.loads(canonical(envelope))
    sig = out.get("signature")
    if sig and sig.get("sig_alg") in LOCAL_ONLY_ALGS:
        out["signature"] = None
        receipt = Receipt.from_dict(out["receipt"])
        limits = ("LOCAL_SIGNATURE_STRIPPED", "NOT_THIRD_PARTY_VERIFIABLE_SIGNATURE")
        missing = tuple(entry for entry in limits if entry not in receipt.does_not_prove())
        if receipt.schema == LEGACY_SCHEMA:
            # v3 deliberately did not bind its honesty list. Preserve that
            # historical export shape and, critically, its signed preimage.
            out["receipt"]["does_not_prove"].extend(missing)
        else:
            extras = receipt.extra_does_not_prove + missing
            out["receipt"] = replace(receipt, extra_does_not_prove=extras).to_dict()
    return out
