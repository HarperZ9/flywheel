"""tree_head.py -- sign the tree head, so append-only stops being our word.

Phase 1C Task 2 was named "consistency proofs and signed tree head". The
consistency proofs landed and are tested, including the doctored-log attack. The
head did not: `Ledger.head()` returns a plain dict, and `grep sign ledger.py`
finds one hit, in a docstring. This module closes that, and it exists because of
two outside documents rather than because of a test failure.

RFC 9162 (Certificate Transparency 2.0) obsoletes the RFC 6962 that `merkle.py`
implements. The `0x00` leaf / `0x01` node domain separation is unchanged, so the
tree code stays correct. What 9162 adds is at the record level: `log_id` in both
proof structures, and a `TreeHeadDataV2` carrying a timestamp inside a
`SignedTreeHeadDataV2` wrapper. The Sigstore client spec says why: a verifier
validates inclusion against a SIGNED head, and should obtain that head in a way
that prevents the log from equivocating.

Equivocation is a log showing two different views to two different readers. Our
answer is the contest channel plus a head a stranger keeps. But a consistency
proof between two roots the PRESENTER chose only shows the presenter can produce
a self-consistent pair. Without a signature over the head, a stranger holding an
old head is trusting us rather than checking us, and anti-equivocation is
asserted rather than held. That is what this module is for.

Three deliberate choices:

  1. **The ledger never touches key material.** `sign_head` takes a callable and
     a public key. The private key stays wherever the caller keeps it, which is
     the standing rule that a signing key never reaches a receipt, a log, or a
     ledger.
  2. **The timestamp is passed in, never read from the clock.** A signed head is
     not reproducible by construction, and that is fine because the head is an
     attestation ABOUT the tree rather than part of it. The root stays
     timestamp-free, so replaying the tree is unaffected. Reading a clock in here
     would make every caller's output un-pinnable for no gain.
  3. **Domain separation against receipt signatures.** A head signature and a
     receipt signature are both Ed25519 over bytes we chose. Without a distinct
     prefix, a head signature could be presented as a receipt signature or the
     reverse. The prefix makes the two preimage spaces disjoint.

`log_id` is the sha256 of the log's public key, following 9162. It binds the
identity of a log to WHO attests to it rather than to what happens to be inside
it, which is the property that makes a proof non-transferable between logs. A
ledger with no key has no honest log id, so it reports `None` and says so in
`does_not_prove` rather than inventing one from a path.
"""
from __future__ import annotations

import hashlib

from .ed25519_verify import verify, Ed25519Error
from .receipt_fields import canonical

SCHEMA = "flywheel.signed-tree-head/v1"

# Disjoint from anything receipt_sign.py signs over. A signature is only
# meaningful together with the space its preimage came from.
HEAD_DOMAIN = b"flywheel.signed-tree-head/v1\x00"

SIGNED_OVER = ("log_id", "size", "root", "timestamp")

NO_LOG_ID = ("NOT_PROVES_WHICH_LOG: this proof does not name the log it came "
             "from, because the ledger has no signing key. Two proofs from two "
             "logs cannot be told apart once they are in the same folder.")


class TreeHeadError(ValueError):
    """A head that cannot be signed or checked as written."""


def log_id_for(public_key: bytes) -> str:
    """RFC 9162's log id: the sha256 of the log's public key."""
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != 32:
        raise TreeHeadError("an Ed25519 public key is exactly 32 bytes")
    return "sha256:" + hashlib.sha256(bytes(public_key)).hexdigest()


def head_preimage(fields: dict) -> bytes:
    """The exact bytes a head signature covers.

    Canonical JSON over SIGNED_OVER only, so a field added to the envelope later
    cannot silently join or leave what was signed. Missing fields are an error
    rather than an empty string: signing over a head whose size is absent would
    produce a valid signature on a meaningless claim.
    """
    missing = [k for k in SIGNED_OVER if fields.get(k) in (None, "")]
    if missing:
        raise TreeHeadError(f"a head cannot be signed without {missing}")
    return HEAD_DOMAIN + canonical(
        {k: fields[k] for k in SIGNED_OVER}).encode()


def sign_head(head: dict, sign, *, public_key: bytes, timestamp: str) -> dict:
    """Attest to `head` (from `Ledger.head()`), returning a signed head.

    `sign` is a callable taking the preimage bytes and returning 64 signature
    bytes. This module never sees the private key.
    """
    if not callable(sign):
        raise TreeHeadError("sign must be a callable taking bytes")
    if not isinstance(timestamp, str) or not timestamp:
        raise TreeHeadError(
            "a timestamp must be supplied by the caller; this module does not "
            "read the clock, so that a caller can pin its own output")
    fields = {"log_id": log_id_for(public_key),
              "size": head.get("size"), "root": head.get("root"),
              "timestamp": timestamp}
    sig = sign(head_preimage(fields))
    if not isinstance(sig, (bytes, bytearray)) or len(sig) != 64:
        raise TreeHeadError(
            f"an Ed25519 signature is 64 bytes, got {len(sig) if sig else 0}")
    return {"schema": SCHEMA, **fields,
            "signature": bytes(sig).hex(),
            "public_key": bytes(public_key).hex(),
            "sig_alg": "ed25519"}


def check_signed_head(signed: dict, public_key: bytes) -> tuple[bool, str]:
    """(ok, reason). A stranger runs this holding the head and a key they trust.

    The key is an ARGUMENT, never read out of the document being checked.
    Verifying a signature against the public key packaged beside it establishes
    only that whoever wrote the document owns some key, which is not a fact about
    the log.
    """
    if not isinstance(signed, dict):
        return False, "malformed_head: not an object"
    if signed.get("schema") != SCHEMA:
        return False, f"wrong_schema: {signed.get('schema')!r}"
    if signed.get("sig_alg") != "ed25519":
        return False, f"unsupported_sig_alg: {signed.get('sig_alg')!r}"
    try:
        expected = log_id_for(public_key)
    except TreeHeadError as e:
        return False, f"bad_key: {e}"
    if signed.get("log_id") != expected:
        # The head names a different log than this key attests to. Accepting it
        # would let a proof be moved between logs, which is the exact reason RFC
        # 9162 put log_id in the record.
        return False, "log_id_does_not_match_key"
    try:
        preimage = head_preimage(signed)
        sig = bytes.fromhex(signed.get("signature", ""))
    except (TreeHeadError, ValueError, RecursionError) as e:
        # A signed field nested past the interpreter's limit makes canonical()
        # inside head_preimage raise RecursionError, which is not a ValueError. A
        # stranger's check must stay a named (False, reason), not an escape.
        return False, f"malformed_head: {e}"
    if len(sig) != 64:
        return False, "malformed_head: signature is not 64 bytes"
    try:
        ok = verify(bytes(public_key), preimage, sig)
    except Ed25519Error as e:
        return False, f"bad_signature: {e}"
    return (True, "ok") if ok else (False, "bad_signature")


def does_not_prove() -> list[str]:
    """What a signed head still does not establish."""
    return [
        "NOT_PROVES_COMPLETENESS: a signed head attests to the tree the log "
        "chose to build. A log can be honest about everything in it and silent "
        "about what was never added.",
        "NOT_PROVES_NON_EQUIVOCATION_ALONE: one signed head proves one view. "
        "Detecting two views needs the head to be gossiped to someone else, or "
        "contested. The signature is what makes that possible, not what does it.",
        "NOT_PROVES_KEY_OWNERSHIP: the holder of the signing key is whoever "
        "holds it. Binding that key to a person is outside this module.",
    ]
