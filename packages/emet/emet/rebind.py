#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""rebind.py - stripped-credential rebind (SPEC section 18, EXPERIMENTAL).

THE FAILURE MODE. C2PA and every embedded-credential scheme bind provenance to
the artifact IN BAND: the manifest, the signature, the certificate travel INSIDE
the file. Re-encode the image, screenshot it, copy the bytes out of the
container, or strip the metadata block, and the credential is gone. The artifact
is now "orphaned": naked bytes with no surviving proof of where they came from,
and the embedded-credential verifier can only shrug.

THE EMET ANSWER. EMET never bound to embedded metadata in the first place. Its
anchor is the sha256 of the RAW BYTES (section 3), computed out of band and kept
in a store the artifact does not carry. So a stripped artifact is not orphaned to
EMET at all: re-derive the content hash of the naked bytes and look it up. If a
known anchor records that digest, the artifact REBINDS to it - a fresh MATCH,
established with zero dependence on any credential surviving inside the file.

This is content-addressed rebinding. It does not recover a stripped C2PA manifest
(the embedded bytes are genuinely gone); it makes recovering them UNNECESSARY,
because the binding was to the content, not to the wrapper.

THE HONEST LATTICE (the same closed primary lattice as verify, section 2):

  MATCH        the naked bytes re-derive to a digest a known anchor records.
               The artifact is rebound to that anchor out of band.
  DRIFT        the caller asserts the artifact IS a known identity (--claim), an
               anchor for that identity exists, and the bytes hash DIFFERENTLY.
               A confirmed substitution: right name, wrong bytes.
  UNVERIFIABLE no anchor records these bytes, and no claimed identity resolves to
               a mismatch. The HONEST DEFAULT: an unknown artifact is unknown,
               never trusted. Absence of a rebind is not evidence of forgery, and
               it is never a pass.

UNVERIFIABLE is the default and dominates nothing: DRIFT (a confirmed difference)
outranks it, mirroring the primary precedence (section 5). EMET emits a rebind
FACT only; MATCH here is re-derivation, not trust, approval, or release, and maps
to no authority word (Boundary 1). A rebind can be sealed into a portable witness
receipt (section 17) so the FACT travels where the stripped credential could not.

THE REBIND MANIFEST. The out-of-band anchor a stripped artifact rebinds against
is a portable, content-addressed JSON object: a set of {digest -> identity}
records a verifier already holds or fetches over a trusted channel. It is the
standardized, cross-implementable shape of "the anchors I know", distinct from the
implementation-private anchor store (section 15) which cannot travel. Its own
`manifest_id` content-addresses its records so a doctored manifest is detectable
before any rebind is attempted.

This module is stdlib-only and part of the named core (section 10). It reuses the
existing spine: hashlib for the content address, report.canonical() for the byte
form (section 7), and the closed primary lattice (verdict.py) for every token.

EXPERIMENTAL: the rebind command and the emet-rebind-manifest/v1 shape are marked
experimental in this release. The Python reference ships here with conformance
vectors and tests; cross-language (Rust/Node/Go) parity is SPECced as follow-on
(docs/REBIND-SPEC.md) and NOT yet pinned in conformance/vectors.json as a
required capability.
"""
import hashlib
import json

from . import report
from .verdict import governed, LATTICE

MANIFEST_FORMAT = "emet-rebind-manifest/v1"

# Fields excluded from a manifest's content address: manifest_id wraps the body.
_MANIFEST_UNADDRESSED = ("manifest_id",)


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _addressed_manifest_body(manifest):
    return {k: v for k, v in manifest.items() if k not in _MANIFEST_UNADDRESSED}


def manifest_id_hash(manifest):
    """Content address of a rebind manifest: sha256 of the canonical JSON form
    (section 7) with manifest_id excluded. Byte-identical across conforming
    implementations, so a doctored anchor record re-hashes to a different id."""
    body = _addressed_manifest_body(manifest)
    return _sha256_hex(report.canonical(body).encode("utf-8"))


def build_manifest(records, issued_at=None):
    """Build a content-addressed rebind manifest from `records`, a list of
    {"digest": <hex sha256>, "identity": <string>} entries. `issued_at` is the one
    wall-clock field (ISO-8601 Z), injected by the caller so the manifest_id is
    deterministic in tests. Returns the manifest dict; render via report.canonical.

    Each record pins a KNOWN anchor: the content digest of an artifact's raw bytes
    and the identity that anchor stands for. A digest may map to at most one
    identity in a manifest; a duplicate digest with a conflicting identity is a
    build error (an ambiguous anchor cannot ground a rebind)."""
    clean = []
    seen = {}
    for r in records:
        if not isinstance(r, dict):
            raise ValueError("rebind manifest record must be an object")
        digest = r.get("digest")
        identity = r.get("identity")
        if not isinstance(digest, str) or not isinstance(identity, str):
            raise ValueError("rebind manifest record needs string digest + identity")
        digest = digest.lower()
        if digest in seen and seen[digest] != identity:
            raise ValueError(
                "ambiguous anchor: digest " + digest[:16] + " maps to both "
                + repr(seen[digest]) + " and " + repr(identity))
        seen[digest] = identity
        clean.append({"digest": digest, "identity": identity})
    manifest = {
        "format": MANIFEST_FORMAT,
        "issued_at": issued_at,
        "records": clean,
        "notes": (
            "EMET rebind manifest: a portable set of known content anchors "
            "(digest -> identity). It carries facts of re-derivation, never "
            "authority, permission, or a release decision."),
    }
    manifest["manifest_id"] = manifest_id_hash(manifest)
    return manifest


def load_manifest(path):
    """Load and shallow-validate a rebind manifest JSON file. Raises ValueError on
    a malformed file or wrong/absent format tag - callers turn that into
    UNVERIFIABLE, never a traceback."""
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise ValueError("manifest unreadable or malformed: " + type(e).__name__)
    if not isinstance(data, dict) or data.get("format") != MANIFEST_FORMAT:
        raise ValueError("not an " + MANIFEST_FORMAT + " manifest")
    return data


def _index(manifest):
    """Build {digest: identity} and {identity: {digest,...}} views from a manifest,
    skipping malformed records rather than crashing. A manifest a caller loaded via
    load_manifest already passed the format gate; a record inside it that is not a
    well-formed {digest, identity} pair is ignored (it grounds no rebind)."""
    by_digest = {}
    by_identity = {}
    for r in manifest.get("records", []):
        if not isinstance(r, dict):
            continue
        digest = r.get("digest")
        identity = r.get("identity")
        if not isinstance(digest, str) or not isinstance(identity, str):
            continue
        digest = digest.lower()
        by_digest[digest] = identity
        by_identity.setdefault(identity, set()).add(digest)
    return by_digest, by_identity


def rebind(naked_bytes, manifest, claim=None):
    """Rebind stripped naked bytes against a known-anchor manifest.

    Returns (verdict, detail, derived_digest) where verdict is a governed primary
    LATTICE token:

      MATCH        derived digest is recorded in the manifest as a known anchor.
                   detail names the identity the artifact rebinds to.
      DRIFT        `claim` names an identity the manifest anchors, but the naked
                   bytes hash to a DIFFERENT digest than that identity's anchor(s).
                   A confirmed substitution.
      UNVERIFIABLE no anchor records these bytes and no claim resolves to a
                   mismatch. The honest default: unknown stays unknown.

    `manifest` is a manifest dict (already loaded + format-checked, or built by
    build_manifest). `claim`, when given, is the identity the caller asserts this
    artifact IS - the out-of-band assertion (a filename, a human statement, a URL)
    that a stripped artifact no longer carries. It is what lets a wrong-bytes case
    be a confirmed DRIFT rather than merely UNVERIFIABLE. `manifest` integrity is
    NOT re-checked here; callers verify the manifest_id separately (rebind_manifest
    below does)."""
    derived = _sha256_hex(naked_bytes)
    by_digest, by_identity = _index(manifest)
    identity = by_digest.get(derived)
    if identity is not None:
        # The naked bytes re-derive to a known anchor. If a claim was made, it must
        # agree with the anchored identity; a matching-digest-but-wrong-name is a
        # DRIFT (the bytes are known, but not as the claimed thing).
        if claim is not None and claim != identity:
            return (governed(LATTICE, "DRIFT"),
                    "bytes rebind to anchor " + repr(identity) + " but claim was "
                    + repr(claim) + " (right bytes, wrong asserted identity)",
                    derived)
        return (governed(LATTICE, "MATCH"),
                "rebound to anchor " + repr(identity) + " digest=" + derived[:16],
                derived)
    # No anchor for these bytes. Only a CLAIM against a known identity turns this
    # into a confirmed difference; otherwise the artifact is simply unknown.
    if claim is not None and claim in by_identity:
        return (governed(LATTICE, "DRIFT"),
                "claim " + repr(claim) + " is anchored, but bytes hash "
                + derived[:16] + " which no anchor for that identity records "
                "(substituted bytes)",
                derived)
    return (governed(LATTICE, "UNVERIFIABLE"),
            "no known anchor records digest " + derived[:16]
            + (" and claim " + repr(claim) + " is not anchored either"
               if claim is not None else "") + " (E_NO_ANCHOR)",
            derived)


def rebind_manifest(naked_bytes, manifest, claim=None):
    """rebind() with a manifest integrity pre-check. If the manifest's own
    manifest_id does not re-derive from its records (a doctored manifest), the
    rebind is UNVERIFIABLE - a corrupt anchor set cannot ground any judgement, and
    EMET refuses to rebind against it rather than trusting it. Returns the same
    (verdict, detail, derived_digest) triple as rebind()."""
    stored = manifest.get("manifest_id") if isinstance(manifest, dict) else None
    if not isinstance(stored, str):
        return (governed(LATTICE, "UNVERIFIABLE"),
                "manifest_id absent or malformed (E_MANIFEST_UNVERIFIABLE)",
                _sha256_hex(naked_bytes))
    derived_id = manifest_id_hash(manifest)
    if stored != derived_id:
        return (governed(LATTICE, "UNVERIFIABLE"),
                "manifest_id does not re-derive: stored " + stored[:16] + " != "
                + derived_id[:16] + " (E_MANIFEST_TAMPERED)",
                _sha256_hex(naked_bytes))
    return rebind(naked_bytes, manifest, claim=claim)
