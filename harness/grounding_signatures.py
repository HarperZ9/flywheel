"""grounding_signatures.py: close the whole-cone rewrite the pin leaves open.

Three checks already stand between a stored receipt and a MATCH, and each one
closes a strictly smaller hole than the last. `_load_intact` in grounding.py
drops a receipt that no longer hashes to the name it is filed under, which
stops an edit in place. A citation that pins the ancestor digest stops an
editor who rewrites a receipt and refiles it under its new hash, because the
pinned name is then absent from the store.

Neither stops an editor who rewrites the whole cone. Rewrite the ancestor,
refile it under its new hash, then rewrite the citing receipt so its pin names
that new hash, refile that under ITS new hash, and walk up. Every filename
check passes. Every pin resolves. Nothing in the store is inconsistent with
anything else in the store, because the store is now internally consistent
about a history that did not happen. Hashes bind a receipt to its own contents
and cannot bind it to an author.

A signature can. The editor above can recompute every hash in the cone; they
cannot produce a signature over the rewritten hashes without the key.

FIVE DISCIPLINES, each one a way this could have been decoration:

1. THE HASH IS RECOMPUTED FROM THE LOADED ENVELOPE, never read out of the
   sidecar. A verifier that trusted the recorded hash would be checking a
   signature over a number the attacker supplied.

2. THE TRUSTED MAPPING DECIDES WHICH KEY IS AUTHORITATIVE, not the sidecar. A
   sidecar carries a public key so a reader can see which key was claimed, and
   `verify_envelope_signature` uses it for nothing. Verifying against the key
   the sidecar names would establish that the holder of some key signed this,
   which is what an attacker who generated a key an hour ago can also show.

3. ONLY ED25519. An HMAC sidecar is refused by name rather than ignored: it
   asks a reader to hold the signing secret, and a reader holding the signing
   secret is not checking anyone's work but their own.

4. ABSENT AND INVALID ARE DIFFERENT FACTS. An unsigned store and a forged
   signature both fail closed, and a reader who cannot tell them apart cannot
   tell an incomplete rollout from an attack.

5. THE DEFAULT PROVES NOTHING NEW. `trusted_keys=None` in resolve_ancestors is
   the behaviour that shipped before this module, and it is still the default,
   because turning this on without a signed store would turn every ancestor
   UNVERIFIABLE. Opt in by naming keys.

WHAT THIS DOES NOT ESTABLISH, stated where the claim is:

  - It says a holder of a trusted key signed these exact bytes. It says nothing
    about whether the receipt was true when it was signed. A signature over a
    wrong measurement is a signed wrong measurement.
  - An attacker who holds the signing key rewrites the cone and re-signs it,
    and every check here passes. The key material is the boundary, and it is
    not defended here.
  - A cone signed by one key and read by a verifier who obtained that key from
    the same person who wrote the receipts has learned that the store is
    self-consistent, which it already knew. Key distribution is out of scope
    and is not solved by pointing at it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .ed25519_verify import verify as _ed_verify, Ed25519Error
from .envelope import ProofEnvelope

SCHEMA = "flywheel.envelope-signature/v1"

#: A sidecar sits beside the receipt it covers, under the same stem.
SIDECAR_SUFFIX = ".sig.json"

NO_SIDECAR = "no signature sidecar beside this receipt"
MALFORMED = "signature sidecar is not readable as this schema"
WRONG_SCHEMA = "signature sidecar declares a schema this verifier does not know"
LOCAL_ONLY = ("signature sidecar uses a local-only algorithm, which a reader "
              "could only check by holding the signing secret")
UNKNOWN_ALG = "signature sidecar names an algorithm this verifier does not know"
UNTRUSTED_KEY = "signature sidecar names a key_id that is not in the trusted set"
COVERS_OTHER = ("signature sidecar covers a different receipt than the one it "
                "sits beside")
INVALID = "signature does not verify against the trusted key for this key_id"


def signed_bytes(task_id: str, content_hash: str) -> bytes:
    """What a signature over a stored receipt covers.

    The task id travels with the hash so a signature cannot be lifted from one
    receipt onto another that happens to share a content hash. Sixteen hex
    characters is a small space to be arguing about, and binding the id costs a
    line.

    The schema string is in the message rather than only in the file, so a
    signature made for this purpose cannot be replayed as a signature made for
    a different one under a future schema.
    """
    return ("%s\n%s\n%s" % (SCHEMA, task_id, content_hash)).encode("utf-8")


def sidecar_path(envelope_path: str | Path) -> Path:
    """The sidecar for a stored receipt, beside it and named after it."""
    p = Path(envelope_path)
    return p.with_name(p.stem + SIDECAR_SUFFIX)


def sidecar_document(*, task_id: str, content_hash: str, signature: bytes,
                     public_key: bytes, key_id: str) -> dict:
    """The sidecar a signer writes. Building it here keeps one shape.

    This module does not sign, for the reason receipt_sign.py gives: a verifier
    must need nothing, and a pure-Python signer in a verification module is an
    invitation to generate keys with an unaudited RNG. The caller brings the
    signature.
    """
    if len(signature) != 64:
        raise ValueError("an ed25519 signature is 64 bytes")
    if len(public_key) != 32:
        raise ValueError("an ed25519 public key is 32 bytes")
    if not key_id:
        raise ValueError("a signature needs a key_id so it can be rotated")
    return {
        "schema": SCHEMA,
        "task_id": task_id,
        "content_hash": content_hash,
        "sig_alg": "ed25519",
        "key_id": key_id,
        "sig": bytes(signature).hex(),
        # For a reader to see which key was claimed. Discipline 2: it decides
        # nothing. The trusted mapping is what is verified against.
        "public_key": bytes(public_key).hex(),
    }


def _read_sidecar(path: Path) -> tuple[dict | None, str]:
    if not path.is_file():
        return None, NO_SIDECAR
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, MALFORMED
    if not isinstance(doc, dict):
        return None, MALFORMED
    if doc.get("schema") != SCHEMA:
        return None, WRONG_SCHEMA
    return doc, ""


def _named_alg(doc: dict) -> str:
    alg = doc.get("sig_alg")
    if alg == "ed25519":
        return ""
    if isinstance(alg, str) and alg.startswith("hmac"):
        return LOCAL_ONLY
    return UNKNOWN_ALG


def verify_envelope_signature(
        envelope: ProofEnvelope, envelope_path: str | Path,
        trusted_keys: dict[str, bytes],
) -> tuple[bool, str]:
    """(ok, reason). A false is always named; this never raises on a bad file.

    `trusted_keys` maps key_id to a 32-byte Ed25519 public key. An empty
    mapping trusts nothing and every receipt fails, which is the honest reading
    of "signatures are required and no key is trusted" rather than a shortcut
    to a pass.
    """
    doc, why = _read_sidecar(sidecar_path(envelope_path))
    if doc is None:
        return False, why
    bad_alg = _named_alg(doc)
    if bad_alg:
        return False, bad_alg

    # Discipline 1. The hash comes from the receipt on disk, and the sidecar
    # only gets to agree with it.
    actual = envelope.content_hash()
    if doc.get("content_hash") != actual or doc.get("task_id") != envelope.task_id:
        return False, COVERS_OTHER

    # Discipline 2. The sidecar's own public_key is read for nobody's benefit
    # but a human reader's.
    key = trusted_keys.get(str(doc.get("key_id", "")))
    if key is None:
        return False, UNTRUSTED_KEY
    try:
        sig = bytes.fromhex(str(doc.get("sig", "")))
    except ValueError:
        return False, MALFORMED
    if len(sig) != 64 or len(key) != 32:
        return False, MALFORMED
    try:
        ok = _ed_verify(bytes(key), signed_bytes(envelope.task_id, actual), sig)
    except (Ed25519Error, ValueError):
        return False, INVALID
    return (True, "") if ok else (False, INVALID)
