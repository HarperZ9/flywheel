"""Authority audit log — append-only JSONL trail of gate checks.

Every gate check is recorded with operator fingerprint, entitlement,
verdict, and timestamp. The log is the accountability layer: it answers
"who was authorized to do what, when, and what was denied."

Log location: ~/.behavior-transform/authority-audit.jsonl
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = "behavior-transform.authority-audit.v1"


def _audit_dir() -> Path:
    d = Path.home() / ".behavior-transform"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _audit_path() -> Path:
    return _audit_dir() / "authority-audit.jsonl"


@dataclass(frozen=True)
class AuditEntry:
    """Single audit log entry."""
    timestamp: float
    gate: str
    entitlement: str
    allowed: bool
    reason: str
    operator_fingerprint: str
    machine_fingerprint: str
    surface: str
    capsule_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "timestamp": self.timestamp,
            "gate": self.gate,
            "entitlement": self.entitlement,
            "allowed": self.allowed,
            "reason": self.reason,
            "operator_fingerprint": self.operator_fingerprint,
            "machine_fingerprint": self.machine_fingerprint,
            "surface": self.surface,
            "capsule_sha256": self.capsule_sha256[:12] + "..." if self.capsule_sha256 else "",
        }


def record_gate_check(
    gate: str,
    entitlement: str,
    allowed: bool,
    reason: str,
    operator_fingerprint: str = "",
    machine_fingerprint: str = "",
    surface: str = "",
    capsule_sha256: str = "",
    log_path: Path | None = None,
) -> AuditEntry:
    """Append a gate check to the audit log."""
    entry = AuditEntry(
        timestamp=time.time(),
        gate=gate,
        entitlement=entitlement,
        allowed=allowed,
        reason=reason,
        operator_fingerprint=operator_fingerprint,
        machine_fingerprint=machine_fingerprint,
        surface=surface,
        capsule_sha256=capsule_sha256,
    )
    path = log_path or _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")
    return entry


def read_audit_log(
    log_path: Path | None = None,
    limit: int = 100,
    gate: str | None = None,
    allowed: bool | None = None,
) -> list[dict[str, Any]]:
    """Read recent audit entries with optional filtering."""
    path = log_path or _audit_path()
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if gate is not None and entry.get("gate") != gate:
            continue
        if allowed is not None and entry.get("allowed") != allowed:
            continue
        entries.append(entry)

    return entries[-limit:]


def audit_summary(
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Produce a summary of the audit log."""
    entries = read_audit_log(log_path=log_path, limit=10000)
    if not entries:
        return {"total": 0, "allowed": 0, "denied": 0, "gates": {}}

    total = len(entries)
    allowed_count = sum(1 for e in entries if e.get("allowed"))
    denied_count = total - allowed_count

    gates: dict[str, dict[str, int]] = {}
    for e in entries:
        g = e.get("gate", "unknown")
        if g not in gates:
            gates[g] = {"allowed": 0, "denied": 0}
        if e.get("allowed"):
            gates[g]["allowed"] += 1
        else:
            gates[g]["denied"] += 1

    recent_denials = [
        e for e in entries[-20:] if not e.get("allowed")
    ]

    return {
        "total": total,
        "allowed": allowed_count,
        "denied": denied_count,
        "denial_rate": round(denied_count / total, 3) if total else 0,
        "gates": gates,
        "recent_denials": recent_denials[-5:],
    }
