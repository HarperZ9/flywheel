# SPDX-License-Identifier: MIT
"""Pure-stdlib `engine-receipt/1` verifier and Flywheel JSONL ledger bridge (N56).

Recomputes `subject_sha256`, `claim_sha256`, and `envelope_sha256` bit-exactly
against the `engine-receipt/1` contract, optionally re-hashes listed artifacts on
disk, and appends verified `MATCH` receipts into an append-only prev-hash JSONL
ledger committed with an RFC 6962 Merkle root.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ENGINE_RECEIPT_SCHEMA = "engine-receipt/1"
LEDGER_ENTRY_SCHEMA = "flywheel.rsi-ledger-entry/v1"

HONEST_SCOPE_LIMIT = (
    "Verifies `engine-receipt/1` SHA-256 digests, optional HMAC tags, optional disk "
    "artifact hashes, and append-only RFC 6962 ledger integrity offline; it does not "
    "re-execute the original oracle command or verify external key custody."
)


def _canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return "sha256:" + h.hexdigest(), size


def _rfc6962_root(leaves: Sequence[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    hashes = [hashlib.sha256(b"\x00" + leaf).digest() for leaf in leaves]

    def _mth(items: list[bytes]) -> bytes:
        n = len(items)
        if n == 1:
            return items[0]
        k = 1
        while k * 2 < n:
            k *= 2
        return hashlib.sha256(b"\x01" + _mth(items[:k]) + _mth(items[k:])).digest()

    return _mth(hashes)


def compute_engine_receipt_digests(
    subject: Mapping[str, Any],
    claim: Mapping[str, Any],
    *,
    hmac_key: str | None = None,
) -> dict[str, str | None]:
    """Compute canonical `subject_sha256`, `claim_sha256`, and `envelope_sha256`."""
    subj_sha = _sha256_prefixed(_canonical_bytes(dict(subject)))
    claim_sha = _sha256_prefixed(_canonical_bytes(dict(claim)))
    seal = {"schema": ENGINE_RECEIPT_SCHEMA, "subject_sha256": subj_sha, "claim_sha256": claim_sha}
    env_sha = _sha256_prefixed(_canonical_bytes(seal))
    sig: str | None = None
    if hmac_key:
        sig = "hmac-sha256:" + hmac.new(
            hmac_key.encode("utf-8"), _canonical_bytes(seal), hashlib.sha256
        ).hexdigest()
    return {
        "subject_sha256": subj_sha,
        "claim_sha256": claim_sha,
        "envelope_sha256": env_sha,
        "signature": sig,
    }


def _check_artifact_files(
    receipt: Mapping[str, Any],
    subject: Mapping[str, Any],
    artifact_root: Path | None,
    errors: list[str],
) -> None:
    art_paths = receipt.get("artifact_paths") or {}
    for item in subject.get("artifacts", []):
        rel = str(item.get("rel_path", ""))
        disk = (Path(artifact_root) / rel) if artifact_root is not None else Path(str(art_paths.get(rel, rel)))
        if not disk.is_file():
            errors.append(f"ARTIFACT_MISSING:{rel}")
            continue
        actual_sha, actual_size = _sha256_file(disk)
        if actual_sha != item.get("sha256") or actual_size != item.get("bytes"):
            errors.append(f"ARTIFACT_HASH_MISMATCH:{rel}")


def verify_engine_receipt(
    receipt: Mapping[str, Any],
    *,
    check_files: bool = False,
    artifact_root: Path | None = None,
    require_match: bool = True,
    hmac_key: str | None = None,
) -> tuple[bool, list[str]]:
    """Fail-closed offline verification of an `engine-receipt/1` envelope."""
    errors: list[str] = []
    if receipt.get("schema") != ENGINE_RECEIPT_SCHEMA:
        errors.append(f"SCHEMA_MISMATCH:{receipt.get('schema')}")
    verdict = str(receipt.get("verdict", ""))
    if require_match and verdict != "MATCH":
        errors.append(f"VERDICT_NOT_MATCH:{verdict}")
    subject = receipt.get("subject")
    if not isinstance(subject, Mapping):
        return False, errors + ["MISSING_SUBJECT"]
    oracle = receipt.get("oracle")
    oracle_claim = (
        {k: oracle.get(k) for k in ("exit_code", "stdout_sha256", "stderr_sha256", "pass_lines", "fail_lines")}
        if isinstance(oracle, Mapping)
        else None
    )
    claim = {"subject": dict(subject), "verdict": verdict, "oracle": oracle_claim, "scope": receipt.get("scope")}
    expected = compute_engine_receipt_digests(subject, claim, hmac_key=hmac_key)
    digests = receipt.get("digests")
    if not isinstance(digests, Mapping):
        return False, errors + ["MISSING_DIGESTS"]
    for field in ("subject_sha256", "claim_sha256", "envelope_sha256"):
        if digests.get(field) != expected[field]:
            errors.append(f"DIGEST_MISMATCH:{field}")
    if hmac_key and digests.get("signature") != expected["signature"]:
        errors.append("HMAC_SIGNATURE_MISMATCH")
    if check_files:
        _check_artifact_files(receipt, subject, artifact_root, errors)
    return len(errors) == 0, errors


def append_verified_receipt_to_ledger(
    ledger_path: Path,
    receipt: Mapping[str, Any],
    *,
    check_files: bool = False,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Verify an `engine-receipt/1` fail-closed and append a chained entry to JSONL."""
    ok, errors = verify_engine_receipt(
        receipt, check_files=check_files, artifact_root=artifact_root, require_match=True
    )
    if not ok:
        raise ValueError(f"refusing unverified receipt: {errors}")

    prev_sha = "genesis"
    seen_claims: set[str] = set()
    if ledger_path.is_file():
        for raw in ledger_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            seen_claims.add(str(row.get("claim_sha256", "")))
            prev_sha = str(row.get("entry_sha256", ""))

    claim_sha = str(receipt["digests"]["claim_sha256"])
    if claim_sha in seen_claims:
        raise ValueError(f"DUPLICATE_CLAIM_REPLAY:{claim_sha}")

    body = {
        "schema": LEDGER_ENTRY_SCHEMA,
        "engine": receipt["subject"]["engine"],
        "task_id": receipt["subject"]["task_id"],
        "verdict": receipt["verdict"],
        "claim_sha256": claim_sha,
        "envelope_sha256": receipt["digests"]["envelope_sha256"],
        "prev_entry_sha256": prev_sha,
    }
    entry = {**body, "entry_sha256": _sha256_prefixed(_canonical_bytes(body))}
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("ab") as fh:
        fh.write(_canonical_bytes(entry) + b"\n")
    return entry


def verify_receipt_ledger(ledger_path: Path) -> tuple[bool, str, str]:
    """Re-verify every prev-hash link and compute the RFC 6962 Merkle root of a JSONL ledger."""
    if not ledger_path.is_file():
        return False, "LEDGER_NOT_FOUND", ""
    raw_lines = [ln for ln in ledger_path.read_bytes().splitlines() if ln.strip()]
    if not raw_lines:
        return False, "EMPTY_LEDGER", ""

    expected_prev = "genesis"
    seen_claims: set[str] = set()
    for idx, raw in enumerate(raw_lines):
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, f"MALFORMED_JSON_AT_{idx}", ""
        if row.get("schema") != LEDGER_ENTRY_SCHEMA:
            return False, f"SCHEMA_MISMATCH_AT_{idx}", ""
        if row.get("prev_entry_sha256") != expected_prev:
            return False, f"CHAIN_LINK_BROKEN_AT_{idx}", ""
        body = {k: v for k, v in row.items() if k != "entry_sha256"}
        if row.get("entry_sha256") != _sha256_prefixed(_canonical_bytes(body)):
            return False, f"ENTRY_DIGEST_TAMPERED_AT_{idx}", ""
        claim_sha = str(row.get("claim_sha256", ""))
        if claim_sha in seen_claims:
            return False, f"DUPLICATE_CLAIM_AT_{idx}", ""
        seen_claims.add(claim_sha)
        expected_prev = str(row["entry_sha256"])

    root_hex = "sha256:" + _rfc6962_root(raw_lines).hex()
    return True, "MATCH", root_hex
