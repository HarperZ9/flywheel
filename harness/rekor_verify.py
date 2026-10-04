"""rekor_verify.py -- recheck a Sigstore Rekor anchor offline, stdlib only.

A Rekor anchor puts one `hashedrekord` entry into Sigstore's public transparency
log: the SHA-512 of an artifact, an Ed25519ph signature over it, and the public
key. Nothing else goes in. The log is run by the Sigstore project, not by the
author, so the entry is a witness the author cannot quietly redo: Rekor signs a
timestamp for it, and the entry sits inside a Merkle tree whose head Rekor signs
and that monitors copy.

This module rechecks a stored anchor record with no network:

  1. the entry body is the `hashedrekord` for THESE bytes (sha512 matches),
     carrying THIS public key, with an Ed25519ph signature that verifies;
  2. the signed entry timestamp (SET) verifies under the PINNED Rekor key, over
     the body, the integrated time, the log ID and the log index;
  3. the inclusion proof recomputes the root in the checkpoint, and the
     checkpoint is signed by the pinned Rekor key.

The Rekor key is pinned here, in code, not read from the record: a record that
carried its own log key would only show it agrees with itself. `verify_record`
raises nothing; every failure is a named reason.
"""
from __future__ import annotations

import base64
import hashlib
import json

from . import ed25519_verify, ed25519ph_verify, p256_verify

SCHEMA = "flywheel.rekor-anchor/v1"

# Sigstore's public-good Rekor v1 instance. Fetched 2026-10-04 from
# https://rekor.sigstore.dev/api/v1/log/publicKey; the log ID is sha256 of the
# key's DER, which `pinned_log_id()` recomputes so the two cannot drift apart.
REKOR_URL = "https://rekor.sigstore.dev"
REKOR_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwr
kBbmLSGtks4L3qX6yYY0zufBnhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw==
-----END PUBLIC KEY-----
"""
REKOR_LOG_ID = "c0d23d6ad406973f9559f3ba2d1ca01f84147d8ffc5b8445c224f98b9591801d"
CHECKPOINT_ORIGIN_PREFIX = "rekor.sigstore.dev - "

# The DER prefix of an Ed25519 SubjectPublicKeyInfo (RFC 8410).
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def pinned_log_id() -> str:
    return hashlib.sha256(p256_verify.pem_to_der(REKOR_PUBLIC_KEY_PEM)).hexdigest()


def ed25519_public_pem(raw: bytes) -> str:
    """The PKIX PEM Rekor expects for a raw 32-byte Ed25519 public key."""
    b64 = base64.b64encode(_ED25519_SPKI_PREFIX + bytes(raw)).decode()
    return f"-----BEGIN PUBLIC KEY-----\n{b64}\n-----END PUBLIC KEY-----\n"


def ed25519_raw_from_pem(pem: str) -> bytes:
    der = p256_verify.pem_to_der(pem)
    if len(der) != 44 or not der.startswith(_ED25519_SPKI_PREFIX):
        raise ValueError("not an Ed25519 SubjectPublicKeyInfo")
    return der[len(_ED25519_SPKI_PREFIX):]


def hashedrekord_entry(artifact: bytes, signature: bytes, public_key: bytes) -> dict:
    """The proposed entry: sha512 of the artifact, signature, key. No content."""
    return {
        "apiVersion": "0.0.1", "kind": "hashedrekord",
        "spec": {
            "data": {"hash": {"algorithm": "sha512",
                              "value": hashlib.sha512(bytes(artifact)).hexdigest()}},
            "signature": {
                "content": base64.b64encode(bytes(signature)).decode(),
                "publicKey": {"content": base64.b64encode(
                    ed25519_public_pem(public_key).encode()).decode()},
            },
        },
    }


# --- RFC 6962 / RFC 9162 Merkle inclusion ------------------------------------

def leaf_hash(entry: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + entry).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def root_from_inclusion(index: int, size: int, leaf: bytes, path: list[bytes]) -> bytes | None:
    """RFC 9162 section 2.1.3.2. None when the path length does not fit the tree."""
    if not 0 <= index < size:
        return None
    fn, sn, r = index, size - 1, leaf
    for p in path:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = _node(p, r)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


# --- signed entry timestamp and checkpoint -----------------------------------

def set_payload(body_b64: str, integrated_time: int, log_id: str, log_index: int) -> bytes:
    """The canonical JSON Rekor signs as the SET (keys sorted, no whitespace)."""
    return json.dumps({"body": body_b64, "integratedTime": integrated_time,
                       "logID": log_id, "logIndex": log_index},
                      sort_keys=True, separators=(",", ":")).encode()


# A signed-note signature line starts with U+2014 and a space (the note format's
# own marker), escaped here so the source stays ASCII.
_SIG_LINE = "\N{EM DASH} "


def parse_checkpoint(text: str) -> dict | None:
    """Split a signed note into origin, size, root and its signature lines."""
    note, sep, sigs = text.partition("\n\n")
    if not sep:
        return None
    lines = note.split("\n")
    if len(lines) < 3:
        return None
    try:
        size = int(lines[1])
        root = base64.b64decode(lines[2], validate=True)
    except ValueError:
        return None
    signatures = []
    for ln in sigs.split("\n"):
        if ln.startswith(_SIG_LINE):
            name, _, b64 = ln[2:].rpartition(" ")
            try:
                raw = base64.b64decode(b64, validate=True)
            except ValueError:
                return None
            signatures.append({"name": name, "hint": raw[:4], "sig": raw[4:]})
    return {"origin": lines[0], "size": size, "root": root,
            "signed": (note + "\n").encode(), "signatures": signatures}


def _checkpoint_ok(cp: dict, log_key, log_id: bytes) -> bool:
    for s in cp["signatures"]:
        if s["hint"] == log_id[:4]:
            try:
                if p256_verify.verify(log_key, cp["signed"], s["sig"]):
                    return True
            except p256_verify.P256Error:
                return False
    return False


# --- the record check --------------------------------------------------------

def _body_reasons(body: dict, artifact: bytes, public_key: bytes) -> list[str]:
    if body.get("kind") != "hashedrekord" or body.get("apiVersion") != "0.0.1":
        return ["BODY_NOT_HASHEDREKORD"]
    spec = body.get("spec") or {}
    h = (spec.get("data") or {}).get("hash") or {}
    reasons = []
    if h.get("algorithm") != "sha512" or h.get("value") != hashlib.sha512(artifact).hexdigest():
        reasons.append("ARTIFACT_HASH_DIFFERS")
    sig = spec.get("signature") or {}
    try:
        pem = base64.b64decode((sig.get("publicKey") or {}).get("content", "")).decode()
        key = ed25519_raw_from_pem(pem)
        signature = base64.b64decode(sig.get("content", ""))
    except ValueError:
        return reasons + ["BODY_KEY_OR_SIGNATURE_MALFORMED"]
    if key != bytes(public_key):
        reasons.append("BODY_KEY_NOT_PINNED_KEY")
    try:
        if not ed25519ph_verify.verify_ph(key, artifact, signature):
            reasons.append("ARTIFACT_SIGNATURE_INVALID")
    except ed25519_verify.Ed25519Error:
        reasons.append("ARTIFACT_SIGNATURE_INVALID")
    return reasons


def verify_record(record: dict, artifact: bytes, public_key: bytes) -> dict:
    """Recheck a stored Rekor anchor against `artifact` and the expected key.

    `public_key` is the raw Ed25519 key the caller pins out of band, never the
    record's own. Returns {"ok", "reasons", "log_index", "integrated_time"}.
    """
    reasons: list[str] = []
    entry = (record or {}).get("entry") or {}
    log_key = p256_verify.public_key_from_spki(p256_verify.pem_to_der(REKOR_PUBLIC_KEY_PEM))
    log_id_raw = bytes.fromhex(REKOR_LOG_ID)
    if pinned_log_id() != REKOR_LOG_ID:
        reasons.append("PINNED_KEY_AND_LOG_ID_DISAGREE")
    if entry.get("logID") != REKOR_LOG_ID:
        reasons.append("LOG_ID_NOT_PINNED")
    body_b64 = entry.get("body", "")
    try:
        body_bytes = base64.b64decode(body_b64, validate=True)
        body = json.loads(body_bytes)
    except ValueError:
        return {"ok": False, "reasons": reasons + ["BODY_UNREADABLE"]}
    reasons += _body_reasons(body, bytes(artifact), public_key)
    ver = entry.get("verification") or {}
    try:
        set_sig = base64.b64decode(ver.get("signedEntryTimestamp", ""), validate=True)
        payload = set_payload(body_b64, entry["integratedTime"], entry["logID"], entry["logIndex"])
        if not p256_verify.verify(log_key, payload, set_sig):
            reasons.append("SET_INVALID")
    except (KeyError, TypeError, ValueError):
        reasons.append("SET_INVALID")
    reasons += _inclusion_reasons(ver.get("inclusionProof") or {}, body_bytes, log_key, log_id_raw)
    return {"ok": not reasons, "reasons": reasons,
            "log_index": entry.get("logIndex"), "integrated_time": entry.get("integratedTime")}


def _inclusion_reasons(proof: dict, body_bytes: bytes, log_key, log_id_raw: bytes) -> list[str]:
    try:
        path = [bytes.fromhex(h) for h in proof["hashes"]]
        root = root_from_inclusion(int(proof["logIndex"]), int(proof["treeSize"]),
                                   leaf_hash(body_bytes), path)
        claimed = bytes.fromhex(proof["rootHash"])
    except (KeyError, TypeError, ValueError):
        return ["INCLUSION_PROOF_MALFORMED"]
    reasons = [] if root == claimed else ["INCLUSION_PROOF_INVALID"]
    cp = parse_checkpoint(proof.get("checkpoint", ""))
    if cp is None:
        return reasons + ["CHECKPOINT_UNREADABLE"]
    if not cp["origin"].startswith(CHECKPOINT_ORIGIN_PREFIX):
        reasons.append("CHECKPOINT_ORIGIN_NOT_PINNED")
    if cp["size"] != int(proof["treeSize"]) or cp["root"] != claimed:
        reasons.append("CHECKPOINT_DISAGREES_WITH_PROOF")
    if not _checkpoint_ok(cp, log_key, log_id_raw):
        reasons.append("CHECKPOINT_SIGNATURE_INVALID")
    return reasons


def does_not_prove() -> list[str]:
    return [
        "NOT_PROVES_CONTENT_IS_CORRECT: the entry shows these bytes existed by the "
        "integrated time, signed by this key. It says nothing about whether what "
        "the bytes claim is true.",
        "NOT_PROVES_THE_KEY_HOLDER_IS_HONEST: whoever holds the key could have "
        "signed and logged other bytes too. Rekor records what it was given.",
        "NOT_PROVES_THE_KEY_IS_THE_AUTHORS: binding the key to a person comes from "
        "where the key is published, not from the log.",
        "NOT_PROVES_REKOR_SHOWS_EVERYONE_ONE_LOG: offline, one checkpoint is one "
        "view. Cross-checking it against a monitor or a later checkpoint is the "
        "online step.",
        "NOT_PROVES_NO_EARLIER_VERSION_EXISTED: the time is an upper bound on when "
        "the bytes existed, never a lower bound.",
    ]
