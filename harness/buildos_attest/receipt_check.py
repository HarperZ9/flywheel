# SPDX-License-Identifier: MIT
"""Fail-closed engine-receipt/1 verifier for Zero-C BuildOS Slices 17 to 20.

Checks receipt schema, MATCH verdict, zero-exit oracle, strict prefixed SHA-256
digests, complete 5-ISA binary coverage (x64-pe, x64-elf, rv64-elf,
aarch64-elf, wasm), and optional live on-disk artifact SHA-256 parity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

HONEST_SCOPE_LIMIT = (
    "Verifies engine-receipt/1 structure, verdict, oracle exit status, strict "
    "digest formatting, 5-ISA binary coverage, and optional on-disk artifact "
    "SHA-256 and byte parity. Does not recompute HMAC signatures or re-execute "
    "the recorded oracle command."
)

ENGINE_RECEIPT_SCHEMA = "engine-receipt/1"
ISA_SUFFIXES: dict[str, str] = {
    "x64-pe": ".exe",
    "x64-elf": ".x64.elf",
    "rv64-elf": ".rv64.elf",
    "aarch64-elf": ".aarch64.elf",
    "wasm": ".wasm",
}
BUILDOS_SLICES: dict[int, str] = {
    17: "buildos_signed_boot_zeroc",
    18: "buildos_cap_sched_zeroc",
    19: "buildos_ipc_vfs_zeroc",
    20: "buildos_e2e_triad_zeroc",
}
_PREFIXED_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def is_strict_int(value: object) -> bool:
    """Return True only for real ints (rejects bool, float, NaN, and Inf)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_finite_number(value: object) -> bool:
    """Return True only for finite int or float values (rejects bool)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def is_hex64(value: object) -> bool:
    """Return True iff value is a 64-character lowercase hex string."""
    return isinstance(value, str) and bool(_HEX64_RE.fullmatch(value))


def is_prefixed_sha256(value: object) -> bool:
    """Return True iff value matches sha256:<64 lowercase hex>."""
    return isinstance(value, str) and bool(_PREFIXED_SHA_RE.fullmatch(value))


@dataclass(frozen=True)
class SliceReceiptReport:
    """Fail-closed verification result for one BuildOS slice receipt."""

    passed: bool
    slice_id: int
    task_id: str
    isa_targets_found: tuple[str, ...]
    artifacts_checked: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize report into a JSON-compatible dictionary."""
        return {
            "passed": self.passed,
            "slice_id": self.slice_id,
            "task_id": self.task_id,
            "isa_targets_found": list(self.isa_targets_found),
            "artifacts_checked": self.artifacts_checked,
            "reasons": list(self.reasons),
        }


def _check_envelope(receipt: Mapping[str, object], reasons: list[str]) -> None:
    if receipt.get("schema") != ENGINE_RECEIPT_SCHEMA:
        reasons.append("INVALID_RECEIPT_SCHEMA")
    if receipt.get("verdict") != "MATCH":
        reasons.append(f"VERDICT_NOT_MATCH:{receipt.get('verdict')}")
    digests = receipt.get("digests")
    if not isinstance(digests, Mapping):
        reasons.append("MISSING_DIGESTS")
    else:
        for field in ("subject_sha256", "claim_sha256", "envelope_sha256"):
            if not is_prefixed_sha256(digests.get(field)):
                reasons.append(f"MALFORMED_DIGEST:{field}")
    oracle = receipt.get("oracle")
    if not isinstance(oracle, Mapping):
        reasons.append("MISSING_ORACLE")
        return
    if not is_strict_int(oracle.get("exit_code")) or oracle.get("exit_code") != 0:
        reasons.append("ORACLE_NOT_ZERO_EXIT")
    if not is_strict_int(oracle.get("fail_lines")) or oracle.get("fail_lines") != 0:
        reasons.append("ORACLE_FAIL_LINES_NONZERO")


def _index_artifacts(subject: Mapping[str, object], reasons: list[str]) -> dict[str, Mapping[str, object]]:
    arts = subject.get("artifacts")
    if not isinstance(arts, list) or not arts:
        reasons.append("MISSING_ARTIFACTS")
        return {}
    index: dict[str, Mapping[str, object]] = {}
    for idx, art in enumerate(arts):
        if not isinstance(art, Mapping) or not isinstance(art.get("rel_path"), str):
            reasons.append(f"INVALID_ARTIFACT:{idx}")
            continue
        rel = str(art["rel_path"])
        if rel in index:
            reasons.append(f"DUPLICATE_ARTIFACT:{rel}")
        if not is_prefixed_sha256(art.get("sha256")):
            reasons.append(f"MALFORMED_ARTIFACT_SHA256:{rel}")
        size = art.get("bytes")
        if not is_strict_int(size) or int(size) <= 0:
            reasons.append(f"INVALID_ARTIFACT_BYTES:{rel}")
        index[rel] = art
    return index


def _check_isa_coverage(slice_id: int, index: Mapping[str, object], reasons: list[str]) -> tuple[str, ...]:
    stem = BUILDOS_SLICES[slice_id]
    names = {Path(rel).name for rel in index}
    found: list[str] = []
    for isa, suffix in ISA_SUFFIXES.items():
        if stem + suffix in names:
            found.append(isa)
        else:
            reasons.append(f"MISSING_ISA_BINARY:{slice_id}:{isa}")
    return tuple(found)


def _check_disk_parity(
    index: Mapping[str, Mapping[str, object]],
    artifact_root: Path,
    reasons: list[str],
) -> int:
    base = artifact_root.resolve()
    checked = 0
    for rel, art in sorted(index.items()):
        path = (base / rel).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            reasons.append(f"ARTIFACT_PATH_ESCAPE:{rel}")
            continue
        if not path.is_file():
            reasons.append(f"MISSING_ARTIFACT_FILE:{rel}")
            continue
        raw = path.read_bytes()
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        declared = art.get("sha256")
        if not isinstance(declared, str) or not hmac.compare_digest(actual, declared):
            reasons.append(f"ARTIFACT_HASH_MISMATCH:{rel}")
        if art.get("bytes") != len(raw):
            reasons.append(f"ARTIFACT_SIZE_MISMATCH:{rel}")
        checked += 1
    return checked


def verify_slice_receipt(
    receipt: Mapping[str, object],
    slice_id: int,
    *,
    artifact_root: Path | None = None,
) -> SliceReceiptReport:
    """Verify one BuildOS Slice 17..20 engine-receipt/1 envelope fail-closed."""
    if not is_strict_int(slice_id) or slice_id not in BUILDOS_SLICES:
        return SliceReceiptReport(False, -1, "", (), 0, (f"UNKNOWN_SLICE:{slice_id}",))
    if not isinstance(receipt, Mapping):
        return SliceReceiptReport(False, slice_id, "", (), 0, ("INVALID_RECEIPT_OBJECT",))
    reasons: list[str] = []
    _check_envelope(receipt, reasons)
    subject = receipt.get("subject")
    if not isinstance(subject, Mapping):
        reasons.append("MISSING_SUBJECT")
        subject = {}
    task_id = str(subject.get("task_id", ""))
    if f"slice{slice_id}" not in task_id:
        reasons.append(f"TASK_ID_SLICE_MISMATCH:{task_id}")
    index = _index_artifacts(subject, reasons)
    found = _check_isa_coverage(slice_id, index, reasons)
    checked = _check_disk_parity(index, artifact_root, reasons) if artifact_root is not None else 0
    unique = tuple(dict.fromkeys(reasons))
    return SliceReceiptReport(not unique, slice_id, task_id, found, checked, unique)


def verify_slice_receipt_file(
    path: Path,
    slice_id: int,
    *,
    artifact_root: Path | None = None,
) -> SliceReceiptReport:
    """Load a receipt JSON file from disk and verify it fail-closed."""
    if not path.is_file():
        return SliceReceiptReport(False, slice_id, "", (), 0, ("MISSING_RECEIPT_FILE",))
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SliceReceiptReport(False, slice_id, "", (), 0, ("INVALID_RECEIPT_JSON",))
    return verify_slice_receipt(receipt, slice_id, artifact_root=artifact_root)
