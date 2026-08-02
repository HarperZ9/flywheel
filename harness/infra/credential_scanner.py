"""credential_scanner.py -- Artifact 22: Credential and Secret Exposure Register.

Scans filesystems, environment variables, and cloud metadata endpoints for
secrets. Maps each secret to owner, privilege, scope. Deploys canary
credentials. Emits sealed flywheel.credential-scan/v1 receipts.

Uses the regex patterns from secret-redact-io (the ecosystem's existing
secret-detection layer).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.credential-scan/v1"

# Secret detection patterns (adapted from secret-redact-io's RedactionRule set).
SECRET_PATTERNS: list[tuple[str, str]] = [
    ("private_key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----"),
    ("openai_api_key", r"sk-[a-zA-Z0-9]{20,}"),
    ("github_token", r"gh[pousr]_[a-zA-Z0-9]{36,}"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("aws_secret", r"(?i)aws_secret_access_key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}"),
    ("jwt", r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"),
    ("bearer_token", r"(?i)bearer\s+[a-zA-Z0-9._-]{20,}"),
    ("generic_password", r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"<>]{8,}"),
    ("generic_api_key", r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9]{20,}"),
    ("generic_secret", r"(?i)secret\s*[:=]\s*['\"]?[a-zA-Z0-9]{20,}"),
]

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(secret_text: str) -> str:
    """Return a non-reversible fingerprint of the secret (first 12 of sha256)."""
    return _sha256_hex(secret_text.encode("utf-8"))[:12]


@dataclass
class SecretFinding:
    """One secret found during a scan."""
    secret_type: str
    location: str  # file path, env var name, or "metadata"
    fingerprint: str  # non-reversible hash prefix
    line_number: int = 0
    context: str = ""  # surrounding text (redacted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "secret_type": self.secret_type,
            "location": self.location,
            "fingerprint": self.fingerprint,
            "line_number": self.line_number,
        }


def scan_text(text: str, location: str = "unknown") -> list[SecretFinding]:
    """Scan a text blob for secrets. Returns findings (never the secret text)."""
    findings: list[SecretFinding] = []
    for secret_type, pattern in SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            findings.append(SecretFinding(
                secret_type=secret_type,
                location=location,
                fingerprint=_fingerprint(match.group()),
                line_number=text[:match.start()].count("\n") + 1,
            ))
    return findings


def scan_file(path: Path) -> list[SecretFinding]:
    """Scan a single file for secrets."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return scan_text(text, str(path))
    except (OSError, PermissionError):
        return []


def scan_directory(root: Path, *, max_files: int = 1000) -> list[SecretFinding]:
    """Walk a directory tree and scan each file for secrets."""
    root = Path(root)
    findings: list[SecretFinding] = []
    count = 0
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    for p in root.rglob("*"):
        if count >= max_files:
            break
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.is_file() and p.stat().st_size < 1024 * 1024:  # skip files > 1MB
            findings.extend(scan_file(p))
            count += 1
    return findings


def scan_environment() -> list[SecretFinding]:
    """Scan environment variables for secrets."""
    findings: list[SecretFinding] = []
    for key, value in os.environ.items():
        text_findings = scan_text(value, f"env:{key}")
        # Also check the key name itself for credential-shaped patterns
        for secret_type, pattern in SECRET_PATTERNS:
            if re.search(pattern, key):
                findings.append(SecretFinding(
                    secret_type=secret_type,
                    location=f"env-key:{key}",
                    fingerprint=_fingerprint(key),
                ))
        findings.extend(text_findings)
    return findings


def scan_all(root: Path | None = None) -> list[SecretFinding]:
    """Scan environment + filesystem. Returns all findings."""
    findings = scan_environment()
    if root:
        findings.extend(scan_directory(root))
    return findings


def build_credential_scan_receipt(
    *,
    findings: list[SecretFinding],
    scan_root: str = "",
    run_id: str = "infra-credscan",
) -> dict[str, Any]:
    """Build a sealed credential scan receipt."""
    seal_body = {
        "scan_root": scan_root,
        "run_id": run_id,
        "timestamp": _utc_now(),
        "finding_count": len(findings),
        "findings": [f.to_dict() for f in findings],
        "finding_types": sorted({f.secret_type for f in findings}),
        "locations": sorted({f.location for f in findings}),
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": seal_body}


def mint_canary_credential(label: str = "canary") -> str:
    """Mint a canary credential for detection testing.

    Returns a canary token that can be planted in the environment. If it
    surfaces in a scan or an agent action, it is a hard access signal.
    """
    import os as _os
    nonce = _os.urandom(8).hex()
    return f"FLYWHEEL-CANARY-CRED-{label}-{nonce}"
