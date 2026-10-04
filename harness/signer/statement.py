"""statement.py -- the only things the signer signs, and the stdlib check for them.

Two statement types, each with its own schema string so a signature over one can
never be presented as the other:

  * an ATTESTATION binds one store record (store id, sequence number, previous
    seal, this seal) to the signer's clock and to the caller identity the signer
    measured;
  * a HEAD says "the last record I signed for this store is seq N with seal S".
    A verifier holding a head detects a store truncated after signing.

The signer never signs caller-chosen bytes. Checking needs only the public key
the verifier pinned, never the key packaged beside the statement.
"""
from __future__ import annotations

import hashlib
import re

from ..ed25519_verify import Ed25519Error, verify
from ..receipt_fields import canonical

ATTESTATION_SCHEMA = "flywheel.signer-attestation/v1"
HEAD_SCHEMA = "flywheel.signer-head/v1"
SEPARATE, SAME, UNATTESTED = "separate-identity", "same-identity", "unattested"
ISOLATION_MODES = (SEPARATE, SAME, UNATTESTED)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_STORE = 4096


class StatementError(ValueError):
    """A request or statement is malformed."""


def key_id_for(public_key: bytes) -> str:
    return "ed25519:" + hashlib.sha256(bytes(public_key)).hexdigest()[:32]


def check_record_fields(store, seq, prev, seal) -> None:
    """Refuse anything but the narrow shape of a record attestation."""
    if not isinstance(store, str) or not store or len(store) > _MAX_STORE:
        raise StatementError("store must be a non-empty string")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise StatementError("seq must be a positive integer")
    if not isinstance(prev, str) or (prev and not _HEX64.match(prev)):
        raise StatementError("prev must be empty or 64 lowercase hex")
    if seq == 1 and prev:
        raise StatementError("the first record has no previous seal")
    if seq > 1 and not prev:
        raise StatementError("every record after the first names its previous seal")
    if not isinstance(seal, str) or not _HEX64.match(seal):
        raise StatementError("seal must be 64 lowercase hex")


def attestation_body(*, store, seq, prev, seal, signed_at, isolation, key_id) -> dict:
    check_record_fields(store, seq, prev, seal)
    return {"schema": ATTESTATION_SCHEMA, "store": store, "seq": seq, "prev": prev,
            "seal": seal, "signed_at": signed_at, "isolation": isolation,
            "key_id": key_id}


def head_body(*, store, seq, seal, rewinds, signed_at, isolation, key_id) -> dict:
    """``rewinds`` lists every operator rewind of this store (journal.py), so a
    rewind is visible to anyone holding a later head."""
    return {"schema": HEAD_SCHEMA, "store": store, "seq": seq, "seal": seal,
            "rewinds": rewinds, "signed_at": signed_at, "isolation": isolation,
            "key_id": key_id}


def preimage(body: dict) -> bytes:
    """The bytes signed: canonical JSON of every field but the signature."""
    return canonical({k: v for k, v in body.items() if k != "signature"}).encode()


def check(statement, public_key: bytes, schema: str) -> tuple[bool, str]:
    """(ok, reason) for one signed statement under a key the caller trusts."""
    if not isinstance(statement, dict):
        return False, "not_an_object"
    if statement.get("schema") != schema:
        return False, f"wrong_schema: {statement.get('schema')!r}"
    if statement.get("key_id") != key_id_for(public_key):
        return False, "key_id_does_not_match_pinned_key"
    try:
        sig = bytes.fromhex(statement.get("signature", ""))
        ok = verify(bytes(public_key), preimage(statement), sig)
    except (Ed25519Error, ValueError, TypeError) as exc:
        return False, f"malformed_signature: {exc}"
    return (True, "ok") if ok else (False, "bad_signature")


def isolation_of(statement: dict) -> str:
    iso = statement.get("isolation") if isinstance(statement, dict) else None
    mode = iso.get("mode") if isinstance(iso, dict) else None
    return mode if mode in ISOLATION_MODES else UNATTESTED
