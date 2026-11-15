#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""witness_receipt.py - SPEC section 17: the portable, offline-verifiable
witness receipt (named core).

A witness receipt is a self-contained JSON object that encodes one or more EMET
verdicts plus the METHOD (hash algorithm, spec version, corpus version if the
producing command pinned one) so a DIFFERENT party can statelessly re-derive and
check it on their OWN machine with ZERO shared state, zero trust in the producer,
and zero network access. Today the anchor store (SPEC section 15) is
implementation-private, so a verdict cannot leave the machine that made it; the
receipt is the standardized, cross-implementable form that CAN travel.

Two independent integrity checks compose here, and neither is a trust decision:

  1. content-addressing (default): receipt_id = sha256(canonical(receipt minus
     receipt_id, signature, and the per-implementation witness block)). Tampering
     ANY governed field re-hashes to a different id, so a doctored receipt is
     detectable with no shared secret. The witness block is excluded because it is
     producer identity (SPEC s.17.2): including it would make the same subject +
     spec + issued_at hash differently in Python vs Rust vs Node.
  2. subject re-derivation (optional): given the subject files on disk, re-hash
     their bytes and compare against the recorded digests. This proves the
     receipt is a POINT-IN-TIME snapshot, not a blanket certificate: when the
     subject changes, re-derivation diverges.

A signature (HMAC-SHA256 over the canonical body) is OPTIONAL and out-of-spec: it
adds integrity assurance only when producer and verifier already share a key
channel. With no key the signature field is null and content-addressing stands
alone. EMET emits witness FACTS only: the receipt-level verdict lives in the
closed RECEIPT lattice (verdict.py) and maps to no authority word.

This module is stdlib-only and part of the named core (SPEC section 10). It reuses
the existing spine: report.canonical() for the byte-identical JSON form (SPEC
section 7), report.self_hash() for the implementation identity (SPEC section 14),
and the closed verdict lattice (verdict.py) for every governed token it emits.
"""
import hashlib
import hmac
import json
import os

from . import report
from .verdict import governed, RECEIPT

FORMAT = "emet-witness-receipt/v1"
IMPLEMENTATION = "emet-python-reference"
RE_DERIVATION_METHOD = "hash"
SIGNATURE_ALGORITHM = "hmac-sha256-optional"
SIGNING_KEY_ENV = "EMET_RECEIPT_SIGNING_KEY"

NOTES = (
    "EMET emits witness facts only. The receipt preserves the closed verdict "
    "lattice and carries no authority, permission, or release decision."
)

# The command envelopes a receipt can be minted from, and the verdict channels
# whose tokens they legitimately carry. verify is the primary source (MATCH /
# DRIFT / UNVERIFIABLE); coherence and corroborate are accepted too. anchor emits
# no verdict, so it contributes subjects but no verdict_record entry.
_SUBJECT_KEYS = ("path", "subject")


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _self_sha256():
    # The implementation identity (SPEC s.14): the artifact-of-record hash over
    # the core source set, reused verbatim from the membrane so the receipt pins
    # the SAME identity the `selftest` command reports.
    from . import membrane
    core_dir = os.path.dirname(os.path.abspath(membrane.__file__))
    return report.self_hash(core_dir, membrane.CORE_SRC)


def _subjects_from_envelope(env, base_dir):
    """Derive the subject list ([{path, sha256}, ...]) from a command envelope.

    The verify/anchor envelopes carry per-path results under results[]; coherence
    carries a single subject. Each subject's recorded sha256 is taken from the
    envelope when present (the got digest verify already computed), else recomputed
    from base_dir. A subject with no derivable digest is recorded with a stable
    reason code rather than dropped, so the receipt never silently omits a target.
    """
    subjects = []
    results = env.get("results")
    if isinstance(results, list) and results:
        for r in results:
            if not isinstance(r, dict):
                continue
            path = r.get("path")
            if not isinstance(path, str):
                continue
            digest = r.get("got") or r.get("sha256")
            if not isinstance(digest, str):
                digest = _recompute(path, base_dir)
            subjects.append(_subject_entry(path, digest))
        return subjects
    # coherence / single-subject envelopes.
    path = env.get("subject")
    if isinstance(path, str):
        digest = env.get("source")
        if not isinstance(digest, str):
            digest = _recompute(path, base_dir)
        subjects.append(_subject_entry(path, digest))
    return subjects


def _subject_entry(path, digest):
    if digest is None:
        return {"path": path, "sha256": None, "reason": "E_NO_DIGEST"}
    return {"path": path, "sha256": digest}


def _recompute(path, base_dir):
    # Re-hash a subject's live bytes from disk; None if unreadable (reported as a
    # reason code by the caller, never a traceback - it is the very tamper event
    # the witness exists to detect).
    full = path if base_dir is None else os.path.join(base_dir, path)
    try:
        with open(full, "rb") as f:
            return _sha256_hex(f.read())
    except OSError:
        return None


def _verdict_records(env):
    """Extract the governed verdict record from a command envelope.

    Each entry maps a subject_index to the command + governed verdict. verify
    carries per-path verdicts under results[]; coherence/corroborate carry a
    single top-level verdict. anchor carries none (it never adjudicates). Every
    token is passed through the closed lattice check indirectly: the envelope was
    produced by governed() at the source, and we copy only the enumerated fields.
    """
    command = env.get("command")
    records = []
    results = env.get("results")
    if isinstance(results, list) and results:
        for i, r in enumerate(results):
            if not isinstance(r, dict):
                continue
            v = r.get("verdict")
            if not isinstance(v, str):
                continue
            rec = {"subject_index": i, "command": command, "verdict": v}
            if isinstance(r.get("want"), str):
                rec["want"] = r["want"]
            if isinstance(r.get("got"), str):
                rec["got"] = r["got"]
            records.append(rec)
        return records
    v = env.get("verdict")
    if isinstance(v, str):
        records.append({"subject_index": 0, "command": command, "verdict": v})
    return records


# Fields EXCLUDED from the content address (SPEC s.17.2). receipt_id and signature
# are excluded because they wrap the body. witness is excluded because it is
# PRODUCER IDENTITY (implementation name + that implementation's own
# artifact-of-record hash, SPEC s.14), which is intrinsically per-implementation:
# including it would make the same subject/verdict/spec/issued_at hash to a
# DIFFERENT id in Python vs Rust vs Node, breaking the s.17.2 re-derivation
# guarantee (which enumerates subject bytes + spec_version + corpus_version +
# issued_at, NOT the producer identity). The witness block still travels in the
# receipt as descriptive metadata; it just does not govern the address.
_UNADDRESSED = ("receipt_id", "signature", "witness")


def _addressed_body(receipt):
    return {k: v for k, v in receipt.items() if k not in _UNADDRESSED}


def receipt_id_hash(receipt):
    """The content address (SPEC s.17.2): sha256 of the canonical JSON form of the
    receipt with receipt_id, signature, and the per-implementation witness block
    EXCLUDED. Byte-identical across conforming implementations because
    report.canonical() pins the byte form and only re-derivation-governed fields
    (subject, verdict_record, issued_at, corpus_*, format, method) are hashed."""
    return _sha256_hex(report.canonical(_addressed_body(receipt)).encode("utf-8"))


def _sign(receipt, signing_key):
    # HMAC-SHA256 over the SAME canonical body the content address covers
    # (id + signature + witness excluded), so signature and address agree.
    return hmac.new(signing_key,
                    report.canonical(_addressed_body(receipt)).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def emit_receipt(env, base_dir=None, now=None, signing_key=None):
    """Build a portable receipt from a command envelope (verify/anchor/coherence/
    corroborate --json output, already parsed to a dict).

    `base_dir` roots relative subject paths for any digest recompute (defaults to
    the process cwd). `now` is the injected issued_at timestamp (ISO-8601 Z) so
    callers - and tests - control the one wall-clock field. `signing_key` (bytes),
    when given, adds the optional HMAC signature; otherwise signature is null.
    Returns the receipt dict; the caller renders it via report.canonical().
    """
    if not isinstance(env, dict):
        raise ValueError("witness receipt requires a parsed command envelope (dict)")
    subjects = _subjects_from_envelope(env, base_dir)
    records = _verdict_records(env)
    receipt = {
        "format": FORMAT,
        "issued_at": now,
        "witness": {
            "implementation": IMPLEMENTATION,
            "spec_version": report.SPEC_VERSION,
            "self_sha256": _self_sha256(),
        },
        "subject": subjects,
        "verdict_record": records,
        "corpus_version": env.get("corpus_version"),
        "corpus_sha256": env.get("corpus_sha256"),
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "re_derivation_method": RE_DERIVATION_METHOD,
        "notes": NOTES,
    }
    # Content-address first, then (optionally) sign the same body. Both cover the
    # receipt minus receipt_id and signature, so they are mutually consistent.
    receipt["signature"] = _sign(receipt, signing_key) if signing_key else None
    receipt["receipt_id"] = receipt_id_hash(receipt)
    return receipt


def load_receipt(path):
    """Load and shallow-validate a receipt JSON file. Raises ValueError on a
    malformed file or a wrong/absent format tag - callers turn that into
    RECEIPT_UNVERIFIABLE, never a traceback."""
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise ValueError("receipt unreadable or malformed: " + type(e).__name__)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not an " + FORMAT + " receipt")
    return data


def _resolve_key(signing_key):
    # Explicit arg wins; else the env var (out-of-spec, optional). None means
    # content-addressing only.
    if signing_key is not None:
        return signing_key
    env = os.environ.get(SIGNING_KEY_ENV)
    return env.encode("utf-8") if env else None


def check_receipt(receipt, base_dir=None, recompute=False, signing_key=None):
    """Stateless offline re-verification. Returns (verdict, detail) where verdict
    is a governed RECEIPT token:

      RECEIPT_VALID        content address re-derives; signature (if any) checks;
                           subjects (if recompute) still hash to recorded digests.
      RECEIPT_TAMPERED     a doctored field (id mismatch), a bad signature, or a
                           changed subject - a CONFIRMED divergence.
      RECEIPT_UNVERIFIABLE the receipt is malformed, or recompute was requested
                           but a subject is unreadable - an INABILITY to check.

    Zero shared state: no anchor store, no log, no network. TAMPERED dominates
    UNVERIFIABLE (a confirmed difference outranks an inability), matching the
    primary lattice precedence (SPEC s.5).
    """
    if not isinstance(receipt, dict) or receipt.get("format") != FORMAT:
        return governed(RECEIPT, "RECEIPT_UNVERIFIABLE"), "not an " + FORMAT + " receipt"
    stored_id = receipt.get("receipt_id")
    if not isinstance(stored_id, str):
        return governed(RECEIPT, "RECEIPT_UNVERIFIABLE"), "receipt_id absent or malformed"
    derived_id = receipt_id_hash(receipt)
    if not hmac.compare_digest(stored_id, derived_id):
        return (governed(RECEIPT, "RECEIPT_TAMPERED"),
                "receipt_id mismatch: stored " + stored_id[:16]
                + " != re-derived " + derived_id[:16])
    # Optional signature check: if the receipt carries one, a key MUST verify it.
    sig = receipt.get("signature")
    key = _resolve_key(signing_key)
    if sig is not None:
        if key is None:
            return (governed(RECEIPT, "RECEIPT_UNVERIFIABLE"),
                    "receipt is signed but no key provided to verify the signature")
        if not hmac.compare_digest(sig, _sign(receipt, key)):
            return governed(RECEIPT, "RECEIPT_TAMPERED"), "signature does not verify"
    # Optional subject re-derivation from live bytes. DRIFT (a changed subject)
    # dominates an unreadable one, mirroring verify's precedence.
    if recompute:
        drift = unver = None
        for s in receipt.get("subject", []):
            if not isinstance(s, dict):
                unver = unver or "malformed subject entry"
                continue
            path = s.get("path")
            recorded = s.get("sha256")
            if not isinstance(path, str) or not isinstance(recorded, str):
                unver = unver or "subject with no recorded digest to re-derive"
                continue
            actual = _recompute(path, base_dir)
            if actual is None:
                unver = unver or ("subject unreadable: " + path)
            elif actual != recorded:
                drift = drift or ("subject digest diverged: " + path)
        if drift is not None:
            return governed(RECEIPT, "RECEIPT_TAMPERED"), drift
        if unver is not None:
            return governed(RECEIPT, "RECEIPT_UNVERIFIABLE"), unver
    return governed(RECEIPT, "RECEIPT_VALID"), "receipt re-derived"
