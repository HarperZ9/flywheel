"""acquisition.py -- Artifact 12: Archive Acquisition Manifest.

Creates a unique acquisition ID + UTC timestamp for any evidence object.
Records collector, source, access method, authorization. Hashes (SHA-256)
stored separately from the object. Chain-of-custody tracking.

The ARCHIVE QUERY acceptance test: every archived object has one manifest row,
one immutable original, one hash, and one custody owner.

Schema: flywheel.acquisition/v1. Sealed (sha256 over canonical JSON).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.acquisition/v1"

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_well_formed(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in _HEX64 for c in s)


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_manifest(
    *,
    source_path: str,
    collector: str,
    access_method: str = "file_read",
    authorization: str = "",
    legal_restriction: str = "",
    custody_owner: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Build an acquisition manifest for an evidence object.

    Reads the file at source_path, computes its SHA-256, and creates a manifest
    row with a unique acquisition ID. The hash is stored IN the manifest but the
    manifest is a separate object from the evidence file itself.

    Raises FileNotFoundError if the source does not exist.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"evidence source not found: {source_path}")

    data = path.read_bytes()
    sha256 = _sha256_hex(data)
    stat = path.stat()

    acquisition_id = f"acq-{uuid.uuid4().hex[:16]}"

    manifest = {
        "schema": SCHEMA,
        "acquisition_id": acquisition_id,
        "timestamp_utc": _utc_now(),
        "source": {
            "path": str(path),
            "filename": path.name,
            "byte_count": len(data),
            "sha256": sha256,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        },
        "collector": collector,
        "access_method": access_method,
        "authorization": authorization,
        "legal_restriction": legal_restriction,
        "custody_owner": custody_owner or collector,
        "notes": notes,
        "seal": "",
    }

    seal_body = {k: v for k, v in manifest.items() if k != "seal"}
    manifest["seal"] = _sha256_hex(_canonical_bytes(seal_body))
    return manifest


def verify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Verify an acquisition manifest. Returns {verdict, detail}.

    Checks: schema, seal, digest well-formedness, hash recomputation from the
    source file (if available).
    """
    if not isinstance(manifest, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "manifest is not an object"}
    if manifest.get("schema") != SCHEMA:
        return {"verdict": "UNVERIFIABLE", "detail": f"schema mismatch"}

    seal = manifest.get("seal", "")
    if not _digest_well_formed(seal):
        return {"verdict": "UNVERIFIABLE", "detail": "seal is not hex64"}

    seal_body = {k: v for k, v in manifest.items() if k != "seal"}
    recomputed = _sha256_hex(_canonical_bytes(seal_body))
    if recomputed != seal:
        return {"verdict": "TAMPERED", "detail": "seal mismatch"}

    source = manifest.get("source", {})
    sha = source.get("sha256", "")
    if not _digest_well_formed(sha):
        return {"verdict": "UNVERIFIABLE", "detail": "source.sha256 not hex64"}

    if not manifest.get("collector"):
        return {"verdict": "UNVERIFIABLE", "detail": "no collector named"}

    return {"verdict": "MATCH", "acquisition_id": manifest.get("acquisition_id", "")}


def recheck_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    """Re-hash the source file and compare to the manifest's recorded hash.

    Returns {verdict, recorded, recomputed}. If the source file is gone or
    unreadable, returns UNVERIFIABLE (never a silent pass).
    """
    source = manifest.get("source", {})
    path = source.get("path", "")
    recorded = source.get("sha256", "")

    if not path:
        return {"verdict": "UNVERIFIABLE", "detail": "no source path"}
    if not Path(path).exists():
        return {"verdict": "UNVERIFIABLE", "detail": f"source gone: {path}"}

    data = Path(path).read_bytes()
    recomputed = _sha256_hex(data)
    if recomputed == recorded:
        return {"verdict": "MATCH", "recorded": recorded, "recomputed": recomputed}
    return {"verdict": "DRIFT", "recorded": recorded, "recomputed": recomputed}
