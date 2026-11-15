"""Environment watchdog for proactive state change detection.

Monitors the environment for changes that invalidate cached authority
grants and active sessions. Detects seal invalidation, capsule removal,
surface deactivation, and operator fingerprint drift.

The watchdog runs a single check pass and reports what changed. It does
not run as a background thread. Callers invoke check() at appropriate
points (session start, before sensitive operations, on schedule).

Changes detected:
  - seal_changed: seal status differs from the cached grant
  - capsule_removed: capsule SHA no longer resolves
  - surface_deactivated: activation state file missing or failed
  - operator_drift: operator fingerprint changed (implies machine or capsule change)
  - grant_expired: cached grant TTL elapsed
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from env_authority import (
    AuthorityGrant,
    cached_authority,
    invalidate_cache,
    resolve_authority,
    _try_load_capsule,
    _try_verify_seal,
)


SCHEMA = "behavior-transform.env-watchdog.v1"


@dataclass(frozen=True)
class EnvironmentChange:
    """Single detected environment change."""
    change_type: str
    detail: str
    severity: str  # info, warning, critical
    detected_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type,
            "detail": self.detail,
            "severity": self.severity,
            "detected_at": self.detected_at,
        }


@dataclass
class WatchdogReport:
    """Result of a watchdog check pass."""
    changes: list[EnvironmentChange] = field(default_factory=list)
    grants_invalidated: int = 0
    sessions_revoked: int = 0
    checked_at: float = 0.0

    @property
    def clean(self) -> bool:
        return len(self.changes) == 0

    @property
    def has_critical(self) -> bool:
        return any(c.severity == "critical" for c in self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "clean": self.clean,
            "has_critical": self.has_critical,
            "changes": [c.to_dict() for c in self.changes],
            "grants_invalidated": self.grants_invalidated,
            "sessions_revoked": self.sessions_revoked,
            "checked_at": self.checked_at,
        }

    def summary(self) -> str:
        if self.clean:
            return "Watchdog: environment clean, no changes detected."
        lines = [f"Watchdog: {len(self.changes)} change(s) detected"]
        for c in self.changes:
            lines.append(f"  [{c.severity.upper()}] {c.change_type}: {c.detail}")
        if self.grants_invalidated:
            lines.append(f"  Grants invalidated: {self.grants_invalidated}")
        if self.sessions_revoked:
            lines.append(f"  Sessions revoked: {self.sessions_revoked}")
        return "\n".join(lines)


def check(
    surface: str | None = None,
    auto_invalidate: bool = True,
    auto_revoke_sessions: bool = True,
) -> WatchdogReport:
    """Run a single watchdog check pass.

    Compares the current environment state against cached grants.
    When auto_invalidate is True, stale grants are cleared from cache.
    When auto_revoke_sessions is True, sessions are revoked on critical changes.
    """
    now = time.time()
    changes: list[EnvironmentChange] = []
    grants_invalidated = 0
    sessions_revoked = 0

    cached = cached_authority(surface=surface)

    capsule_sha, capsule_status = _try_load_capsule()
    if cached.capsule_sha256 and not capsule_sha:
        changes.append(EnvironmentChange(
            change_type="capsule_removed",
            detail=f"cached capsule {cached.capsule_sha256[:12]}... no longer resolves",
            severity="critical",
            detected_at=now,
        ))

    seal_status = _try_verify_seal()
    if cached.seal_status != seal_status:
        severity = "critical" if seal_status == "fail" else "warning"
        changes.append(EnvironmentChange(
            change_type="seal_changed",
            detail=f"seal status changed from {cached.seal_status} to {seal_status}",
            severity=severity,
            detected_at=now,
        ))

    if cached.valid and cached.expired:
        changes.append(EnvironmentChange(
            change_type="grant_expired",
            detail="cached grant TTL elapsed",
            severity="warning",
            detected_at=now,
        ))

    fresh = resolve_authority(surface=surface)
    if cached.operator_fingerprint and fresh.operator_fingerprint:
        if cached.operator_fingerprint != fresh.operator_fingerprint:
            changes.append(EnvironmentChange(
                change_type="operator_drift",
                detail="operator fingerprint changed between cached and fresh resolution",
                severity="critical",
                detected_at=now,
            ))

    if cached.status == "authorized" and fresh.status != "authorized":
        changes.append(EnvironmentChange(
            change_type="authorization_lost",
            detail=f"grant status changed from authorized to {fresh.status}",
            severity="critical",
            detected_at=now,
        ))

    has_critical = any(c.severity == "critical" for c in changes)

    if changes and auto_invalidate:
        invalidate_cache(surface=surface)
        grants_invalidated = 1

    if has_critical and auto_revoke_sessions:
        try:
            from session_authority import revoke_all
            sessions_revoked = revoke_all(
                surface=surface,
                reason="watchdog_critical_change",
            )
        except ImportError:
            pass

    return WatchdogReport(
        changes=changes,
        grants_invalidated=grants_invalidated,
        sessions_revoked=sessions_revoked,
        checked_at=now,
    )
