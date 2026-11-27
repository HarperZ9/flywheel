# SPDX-License-Identifier: MIT
"""Boring-Bridge zero-dependency offline FIPS 180-4 SHA-256 + RFC 6962 verifier (N70).

Seals arbitrary JSON receipt records into a standalone RFC 6962 Merkle proof
bundle and verifies every record digest, inclusion proof, root, and bundle
checksum offline using only Python stdlib and `harness.merkle`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from harness.merkle import inclusion_proof, merkle_root, verify_inclusion
from harness.receipt_fields import canonical

BUNDLE_SCHEMA = "flywheel.boring-bridge-bundle/v1"

HONEST_SCOPE_LIMIT = (
    "Verifies cryptographic SHA-256 payload digests and RFC 6962 Merkle "
    "inclusion offline with zero third-party packages; it does not establish "
    "external witness consensus, timestamp authority, or real-world adoption."
)


def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    """Serialize one JSON record to deterministic canonical UTF-8 bytes."""
    return canonical(dict(record)).encode("utf-8")


def sha256_prefixed(data: bytes) -> str:
    """Return FIPS 180-4 SHA-256 hex digest with `sha256:` prefix."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def seal_boring_bundle(
    records: Sequence[Mapping[str, Any]],
    *,
    bundle_id: str,
) -> dict[str, Any]:
    """Seal a non-empty list of records into an offline-verifiable RFC 6962 bundle."""
    if not bundle_id or not bundle_id.strip():
        raise ValueError("bundle_id must be non-empty")
    if not records:
        raise ValueError("records must be non-empty")

    leaf_bytes = [canonical_record_bytes(rec) for rec in records]
    root = merkle_root(leaf_bytes)
    root_hex = "sha256:" + root.hex()

    entries: list[dict[str, Any]] = []
    for idx, (rec, raw) in enumerate(zip(records, leaf_bytes, strict=True)):
        proof = inclusion_proof(leaf_bytes, idx)
        if not verify_inclusion(raw, idx, len(leaf_bytes), proof, root):
            raise RuntimeError(f"internal RFC 6962 proof self-check failed at index {idx}")
        entries.append({
            "index": idx,
            "payload": dict(rec),
            "payload_sha256": sha256_prefixed(raw),
            "leaf_sha256": sha256_prefixed(b"\x00" + raw),
            "inclusion_proof_hex": [step.hex() for step in proof],
        })

    body: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "rfc": "RFC-6962",
        "bundle_id": bundle_id.strip(),
        "leaf_count": len(leaf_bytes),
        "merkle_root": root_hex,
        "entries": entries,
        "honest_scope_limit": HONEST_SCOPE_LIMIT,
    }
    return {
        **body,
        "bundle_sha256": sha256_prefixed(canonical(body).encode("utf-8")),
    }


def verify_single_record_inclusion(
    record: Mapping[str, Any],
    *,
    index: int,
    leaf_count: int,
    proof_hex: Sequence[str],
    merkle_root_hex: str,
) -> tuple[bool, str]:
    """Verify one record's RFC 6962 Merkle inclusion proof offline."""
    if leaf_count <= 0 or not (0 <= index < leaf_count):
        return False, "INDEX_OUT_OF_RANGE"
    if not merkle_root_hex.startswith("sha256:") or len(merkle_root_hex) != 71:
        return False, "MALFORMED_MERKLE_ROOT"
    try:
        root = bytes.fromhex(merkle_root_hex.removeprefix("sha256:"))
        proof = [bytes.fromhex(step) for step in proof_hex]
    except (ValueError, TypeError):
        return False, "MALFORMED_PROOF_HEX"
    raw = canonical_record_bytes(record)
    if not verify_inclusion(raw, index, leaf_count, proof, root):
        return False, "INCLUSION_PROOF_FAILED"
    return True, "MATCH"


def verify_boring_bundle(
    bundle: Mapping[str, Any],
    *,
    expected_root: str | None = None,
) -> tuple[bool, str]:
    """Fail-closed offline verifier for a `flywheel.boring-bridge-bundle/v1` bundle."""
    if bundle.get("schema") != BUNDLE_SCHEMA:
        return False, "SCHEMA_MISMATCH"
    entries = bundle.get("entries")
    if not isinstance(entries, list) or not entries:
        return False, "EMPTY_OR_MALFORMED_ENTRIES"
    leaf_count = bundle.get("leaf_count")
    if leaf_count != len(entries):
        return False, f"LEAF_COUNT_MISMATCH:{len(entries)}!={leaf_count}"

    root_hex = str(bundle.get("merkle_root", ""))
    if not root_hex.startswith("sha256:") or len(root_hex) != 71:
        return False, "MALFORMED_MERKLE_ROOT"
    if expected_root is not None and root_hex != expected_root:
        return False, "EXPECTED_ROOT_MISMATCH"
    try:
        declared_root = bytes.fromhex(root_hex.removeprefix("sha256:"))
    except ValueError:
        return False, "MALFORMED_MERKLE_ROOT"

    leaf_bytes: list[bytes] = []
    for pos, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or entry.get("index") != pos:
            return False, f"ENTRY_INDEX_MISMATCH:{pos}"
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            return False, f"MALFORMED_PAYLOAD:{pos}"
        raw = canonical_record_bytes(payload)
        if entry.get("payload_sha256") != sha256_prefixed(raw):
            return False, f"PAYLOAD_SHA256_MISMATCH:{pos}"
        if entry.get("leaf_sha256") != sha256_prefixed(b"\x00" + raw):
            return False, f"LEAF_SHA256_MISMATCH:{pos}"
        ok_inc, why_inc = verify_single_record_inclusion(
            payload,
            index=pos,
            leaf_count=len(entries),
            proof_hex=entry.get("inclusion_proof_hex", ()),
            merkle_root_hex=root_hex,
        )
        if not ok_inc:
            return False, f"{why_inc}:{pos}"
        leaf_bytes.append(raw)

    actual_root = merkle_root(leaf_bytes)
    if actual_root != declared_root:
        return False, "MERKLE_ROOT_MISMATCH"

    body = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    expected_bundle_sha = sha256_prefixed(canonical(body).encode("utf-8"))
    if bundle.get("bundle_sha256") != expected_bundle_sha:
        return False, "BUNDLE_SHA256_TAMPERED"
    return True, "MATCH"
