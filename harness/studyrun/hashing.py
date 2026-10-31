"""Hashes: file bytes, canonical JSON, and short forms for ledger lines."""
import hashlib
import json
from pathlib import Path

from .. import canonical_record

FORM = canonical_record.SPEC  # the form new locks and manifests are hashed under
LEGACY_FORM = "studyrun-json/0"  # json.dumps(sort_keys) as the 2026-10-29 prototype wrote it


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj, form=FORM):
    """Canonical text. canonical-record/1 by default (docs/spec/canonical-record.md); the legacy form
    is kept only so a lock written by the prototype, which names no form, still verifies."""
    if form == LEGACY_FORM:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if form != FORM:
        raise ValueError(f"unknown canonical form {form!r}")
    return canonical_record.text(obj)


def sha256_json(obj, form=FORM):
    return hashlib.sha256(canonical(obj, form).encode("utf-8")).hexdigest()


def short(digest):
    """The ledger's short form: first 8 and last 5 hex digits, as FINDINGS.md writes them."""
    return f"{digest[:8]}...{digest[-5:]}"


def hash_paths(paths):
    """{path: sha256} for each existing file; a missing file maps to None."""
    return {str(p): (sha256_file(p) if Path(p).is_file() else None) for p in paths}
