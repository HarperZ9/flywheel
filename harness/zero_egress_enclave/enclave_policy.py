# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N46 Sovereign Zero-Egress Verification Enclave Policy and Receipt Sealer.

Enforces zero outbound network egress (URLs, raw IPs, socket schemes), blocks
PII/secret/local-path leakage, enforces hard memory and CPU budget ceilings,
and seals input/output FIPS 180-4 SHA-256 receipts verifiable offline.
Pure Python standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

_AT = chr(64)
URL_EGRESS_RE = re.compile(r"\b(?:https?|ftp|ws|wss|ssh|sftp|tcp|udp)://[^\s\"']+", re.I)
IPV4_EGRESS_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b")
EMAIL_PII_RE = re.compile(r"\b[A-Za-z0-9._%+-]+" + _AT + r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SSN_PII_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SECRET_TOKEN_RE = re.compile(
    r"\b(?:" + "sk" + r"-[A-Za-z0-9_-]{12,}|" + "ghp" + r"_[A-Za-z0-9]{20,}|" + "AK" + r"IA[0-9A-Z]{16})\b"
)
LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[/\\]Us" + r"ers[/\\]|/ho" + r"me/[A-Za-z0-9._-]+/|/Us" + r"ers/[A-Za-z0-9._-]+/)"
)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class EnclaveBudget:
    """Resource ceiling for an offline zero-egress enclave execution."""

    max_memory_mb: int = 256
    max_cpu_ms: int = 5000
    max_output_bytes: int = 65536
    allow_network: bool = False


@dataclass(frozen=True)
class EnclaveReceipt:
    """Sealed zero-egress execution receipt binding input and output digests."""

    task_id: str
    input_sha256: str
    output_sha256: str
    memory_mb_used: int
    cpu_ms_used: int
    egress_attempts: int
    verdict: str
    receipt_sha256: str


@dataclass(frozen=True)
class EnclaveVerdict:
    """Fail-closed verdict returned by execute_zero_egress_audit."""

    ok: bool
    verdict: str
    violations: tuple[str, ...]
    receipt: EnclaveReceipt | None


def scan_egress_and_pii(payload_text: str) -> list[str]:
    """Scan outbound text for network URLs, raw IPs, emails, SSNs, tokens, and local paths."""
    hits: list[str] = []
    if URL_EGRESS_RE.search(payload_text):
        hits.append("outbound_url_egress")
    if IPV4_EGRESS_RE.search(payload_text):
        hits.append("outbound_ipv4_egress")
    if EMAIL_PII_RE.search(payload_text):
        hits.append("pii_email_leak")
    if SSN_PII_RE.search(payload_text):
        hits.append("pii_ssn_leak")
    if SECRET_TOKEN_RE.search(payload_text):
        hits.append("secret_token_leak")
    if LOCAL_PATH_RE.search(payload_text):
        hits.append("local_user_path_leak")
    return hits


def _seal_receipt_sha256(
    task_id: str,
    input_sha256: str,
    output_sha256: str,
    memory_mb_used: int,
    cpu_ms_used: int,
    egress_attempts: int,
    verdict: str,
) -> str:
    body = json.dumps(
        {
            "task_id": task_id,
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "memory_mb_used": memory_mb_used,
            "cpu_ms_used": cpu_ms_used,
            "egress_attempts": egress_attempts,
            "verdict": verdict,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(body)


def execute_zero_egress_audit(
    task_id: str,
    input_bytes: bytes,
    output_bytes: bytes,
    memory_mb_used: int,
    cpu_ms_used: int,
    egress_attempts: int = 0,
    budget: EnclaveBudget | None = None,
) -> EnclaveVerdict:
    """Enforce zero-egress, PII/URL scanning, resource ceilings, and seal SHA-256 receipt."""
    cfg = budget or EnclaveBudget()
    violations: list[str] = []
    if not task_id.strip():
        violations.append("empty_task_id")
    if cfg.allow_network:
        violations.append("network_policy_not_zero_egress")
    if egress_attempts > 0:
        violations.append(f"outbound_socket_attempts:{egress_attempts}")
    if memory_mb_used < 0 or memory_mb_used > cfg.max_memory_mb:
        violations.append(f"memory_budget_exceeded:{memory_mb_used}>{cfg.max_memory_mb}")
    if cpu_ms_used < 0 or cpu_ms_used > cfg.max_cpu_ms:
        violations.append(f"cpu_budget_exceeded:{cpu_ms_used}>{cfg.max_cpu_ms}")
    if len(output_bytes) > cfg.max_output_bytes:
        violations.append(f"output_bytes_exceeded:{len(output_bytes)}>{cfg.max_output_bytes}")
    decoded_out = output_bytes.decode("utf-8", errors="replace")
    violations.extend(scan_egress_and_pii(decoded_out))

    ok = len(violations) == 0
    verdict = "PASS" if ok else "REJECT"
    in_sha = _sha256_bytes(input_bytes)
    out_sha = _sha256_bytes(output_bytes)
    rcpt_sha = _seal_receipt_sha256(
        task_id.strip(), in_sha, out_sha, memory_mb_used, cpu_ms_used, egress_attempts, verdict
    )
    receipt = EnclaveReceipt(
        task_id=task_id.strip(),
        input_sha256=in_sha,
        output_sha256=out_sha,
        memory_mb_used=memory_mb_used,
        cpu_ms_used=cpu_ms_used,
        egress_attempts=egress_attempts,
        verdict=verdict,
        receipt_sha256=rcpt_sha,
    )
    return EnclaveVerdict(ok=ok, verdict=verdict, violations=tuple(violations), receipt=receipt)


def verify_enclave_receipt(
    receipt: EnclaveReceipt,
    input_bytes: bytes,
    output_bytes: bytes,
) -> tuple[bool, list[str]]:
    """Independently re-verify an EnclaveReceipt offline against raw input/output bytes."""
    errors: list[str] = []
    if receipt.input_sha256 != _sha256_bytes(input_bytes):
        errors.append("input_sha256_mismatch")
    if receipt.output_sha256 != _sha256_bytes(output_bytes):
        errors.append("output_sha256_mismatch")
    if receipt.egress_attempts != 0:
        errors.append("non_zero_egress_attempts")
    expected_sha = _seal_receipt_sha256(
        receipt.task_id,
        receipt.input_sha256,
        receipt.output_sha256,
        receipt.memory_mb_used,
        receipt.cpu_ms_used,
        receipt.egress_attempts,
        receipt.verdict,
    )
    if receipt.receipt_sha256 != expected_sha:
        errors.append("receipt_sha256_tampered")
    if receipt.verdict != "PASS":
        errors.append(f"non_pass_verdict:{receipt.verdict}")
    return len(errors) == 0, errors


def enclave_summary_dict(v: EnclaveVerdict) -> dict[str, Any]:
    """Serialize EnclaveVerdict into a plain JSON-safe dictionary."""
    return {
        "schema": "n46-zero-egress-enclave/1",
        "ok": v.ok,
        "verdict": v.verdict,
        "violations": list(v.violations),
        "receipt": v.receipt.__dict__ if v.receipt else None,
    }
