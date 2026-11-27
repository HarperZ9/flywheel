# SPDX-License-Identifier: MIT
"""Deterministic cross-ISA build and output digest parity verifier.

Verifies that a multi-target build produces valid, non-divergent output
digests across all required architectures (x64-pe, x64-elf, rv64-elf,
aarch64-elf, wasm) and fails closed on missing targets, single-ISA
divergence, non-zero exit codes, or forged binary digests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Verifies deterministic target coverage, output digest consensus, binary "
    "size bounds, and optional raw-byte SHA-256 integrity across supplied "
    "build records. Does not execute target binaries itself or substitute for "
    "hardware execution of each ISA."
)

REQUIRED_TARGETS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class IsaBuildRecord:
    """Measured build and execution digests for a single ISA target."""

    target: str
    binary_sha256: str
    stdout_sha256: str
    binary_bytes: int
    exit_code: int = 0


@dataclass(frozen=True)
class MultiIsaParityReport:
    """Fail-closed result of cross-ISA parity verification."""

    passed: bool
    consensus_stdout_sha256: str | None
    targets_verified: tuple[str, ...]
    missing_targets: tuple[str, ...]
    divergent_targets: tuple[str, ...]
    reasons: tuple[str, ...]
    attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "consensus_stdout_sha256": self.consensus_stdout_sha256,
            "targets_verified": list(self.targets_verified),
            "missing_targets": list(self.missing_targets),
            "divergent_targets": list(self.divergent_targets),
            "reasons": list(self.reasons),
            "attestation_sha256": self.attestation_sha256,
        }


def sha256_hex(data: bytes) -> str:
    """Return lowercase hexadecimal SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def build_record_from_bytes(
    target: str,
    binary_data: bytes,
    stdout_data: bytes,
    *,
    exit_code: int = 0,
) -> IsaBuildRecord:
    """Construct an IsaBuildRecord directly from binary and stdout bytes."""
    return IsaBuildRecord(
        target=target,
        binary_sha256=sha256_hex(binary_data),
        stdout_sha256=sha256_hex(stdout_data),
        binary_bytes=len(binary_data),
        exit_code=exit_code,
    )


def _is_hex64(value: str) -> bool:
    return isinstance(value, str) and bool(_HEX64_RE.fullmatch(value))


def _seal_attestation(
    records: Sequence[IsaBuildRecord],
    passed: bool,
    reasons: Sequence[str],
) -> str:
    payload = {
        "passed": passed,
        "reasons": list(reasons),
        "records": [
            {
                "target": r.target,
                "binary_sha256": r.binary_sha256,
                "stdout_sha256": r.stdout_sha256,
                "binary_bytes": r.binary_bytes,
                "exit_code": r.exit_code,
            }
            for r in sorted(records, key=lambda item: item.target)
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_hex(raw)


def _check_record(
    tgt: str,
    rec: IsaBuildRecord,
    *,
    expected_stdout_sha256: str | None,
    binary_bytes_by_target: Mapping[str, bytes] | None,
    max_binary_bytes: int | None,
    reasons: list[str],
    valid_stdout: dict[str, str],
) -> None:
    if not _is_hex64(rec.binary_sha256):
        reasons.append(f"MALFORMED_BINARY_DIGEST:{tgt}")
    if not _is_hex64(rec.stdout_sha256):
        reasons.append(f"MALFORMED_STDOUT_DIGEST:{tgt}")
    else:
        valid_stdout[tgt] = rec.stdout_sha256
    if rec.binary_bytes <= 0:
        reasons.append(f"INVALID_BINARY_SIZE:{tgt}")
    elif max_binary_bytes is not None and rec.binary_bytes > max_binary_bytes:
        reasons.append(f"BINARY_SIZE_EXCEEDS_LIMIT:{tgt}:{rec.binary_bytes}")
    if rec.exit_code != 0:
        reasons.append(f"NON_ZERO_EXIT:{tgt}:{rec.exit_code}")
    if binary_bytes_by_target is not None:
        raw_bin = binary_bytes_by_target.get(tgt)
        if raw_bin is None:
            reasons.append(f"MISSING_RAW_BINARY:{tgt}")
        else:
            if not hmac.compare_digest(sha256_hex(raw_bin), rec.binary_sha256):
                reasons.append(f"FORGED_BINARY_DIGEST:{tgt}")
            if len(raw_bin) != rec.binary_bytes:
                reasons.append(f"FORGED_BINARY_SIZE:{tgt}")
    if (
        expected_stdout_sha256 is not None
        and _is_hex64(expected_stdout_sha256)
        and _is_hex64(rec.stdout_sha256)
        and not hmac.compare_digest(rec.stdout_sha256, expected_stdout_sha256)
    ):
        reasons.append(f"EXPECTED_STDOUT_MISMATCH:{tgt}")


def _resolve_consensus(
    valid_stdout: dict[str, str],
    req_tuple: tuple[str, ...],
    reasons: list[str],
) -> tuple[str | None, list[str]]:
    distinct = Counter(valid_stdout.values())
    if len(distinct) == 1 and len(valid_stdout) == len(req_tuple) and req_tuple:
        return next(iter(distinct)), []
    if len(distinct) > 1:
        top_digest, top_count = distinct.most_common(1)[0]
        tied = sum(1 for c in distinct.values() if c == top_count) > 1
        div = sorted(valid_stdout) if tied else sorted(t for t, d in valid_stdout.items() if d != top_digest)
        reasons.append("SINGLE_ISA_STDOUT_DIVERGENCE:" + ",".join(div))
        return None, div
    return None, []


def verify_multi_isa_parity(
    records: Sequence[IsaBuildRecord],
    *,
    required_targets: Sequence[str] = REQUIRED_TARGETS,
    expected_stdout_sha256: str | None = None,
    binary_bytes_by_target: Mapping[str, bytes] | None = None,
    max_binary_bytes: int | None = None,
) -> MultiIsaParityReport:
    """Verify cross-ISA build parity fail-closed across all required targets."""
    reasons: list[str] = []
    req_tuple = tuple(required_targets)
    req_set = set(req_tuple)
    if not req_tuple:
        reasons.append("EMPTY_REQUIRED_TARGETS")
    if not records:
        reasons.append("EMPTY_RECORDS")
    by_target: dict[str, IsaBuildRecord] = {}
    for rec in records:
        if rec.target in by_target:
            reasons.append(f"DUPLICATE_TARGET:{rec.target}")
        elif rec.target not in req_set:
            reasons.append(f"UNKNOWN_TARGET:{rec.target}")
        else:
            by_target[rec.target] = rec
    missing = tuple(t for t in req_tuple if t not in by_target)
    if missing:
        reasons.append("MISSING_REQUIRED_TARGETS:" + ",".join(missing))
    if expected_stdout_sha256 is not None and not _is_hex64(expected_stdout_sha256):
        reasons.append("MALFORMED_EXPECTED_STDOUT_DIGEST")
    valid_stdout: dict[str, str] = {}
    for tgt in req_tuple:
        rec = by_target.get(tgt)
        if rec is not None:
            _check_record(
                tgt, rec, expected_stdout_sha256=expected_stdout_sha256,
                binary_bytes_by_target=binary_bytes_by_target,
                max_binary_bytes=max_binary_bytes, reasons=reasons, valid_stdout=valid_stdout,
            )
    consensus, divergent = _resolve_consensus(valid_stdout, req_tuple, reasons)
    passed = not reasons and consensus is not None
    verified = tuple(t for t in req_tuple if t in by_target)
    return MultiIsaParityReport(
        passed, consensus if passed else None, verified, missing,
        tuple(divergent), tuple(reasons), _seal_attestation(records, passed, reasons),
    )
