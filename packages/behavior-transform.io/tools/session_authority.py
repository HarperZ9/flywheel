"""Session-scoped authority binding.

Binds a session to an AuthorityGrant with its own lifecycle. Sessions
have independent TTL from the underlying grant, can be revoked without
revoking the grant, and track activity for audit.

Multiple concurrent sessions on the same machine get separate tokens.
A session token is a SHA-256 digest of (operator_fingerprint, surface,
session_start_time, pid), giving each invocation a unique identity
without requiring external entropy.

Session state persists to ~/.behavior-transform/sessions/ as JSON files.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from env_authority import AuthorityGrant, cached_authority, invalidate_cache


SCHEMA = "behavior-transform.session-authority.v1"
DEFAULT_SESSION_TTL = 1800


def _sessions_dir() -> Path:
    d = Path.home() / ".behavior-transform" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _derive_session_token(
    operator_fingerprint: str,
    surface: str,
    start_time: float,
) -> str:
    raw = f"{operator_fingerprint}:{surface}:{start_time}:{os.getpid()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class SessionState:
    """Live session bound to an authority grant."""
    token: str
    operator_fingerprint: str
    machine_fingerprint: str
    surface: str
    grant_status: str
    seal_status: str
    capsule_sha256: str
    entitlements: list[str]
    started_at: float
    expires_at: float
    revoked: bool = False
    revoked_at: float = 0.0
    revoke_reason: str = ""
    gate_checks: int = 0
    infer_count: int = 0
    last_activity: float = 0.0

    @property
    def active(self) -> bool:
        return (
            not self.revoked
            and self.grant_status == "authorized"
            and time.time() < self.expires_at
        )

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "token": self.token,
            "operator_fingerprint": self.operator_fingerprint,
            "machine_fingerprint": self.machine_fingerprint,
            "surface": self.surface,
            "grant_status": self.grant_status,
            "seal_status": self.seal_status,
            "capsule_sha256": self.capsule_sha256[:12] + "..." if self.capsule_sha256 else "",
            "entitlements": self.entitlements,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "revoke_reason": self.revoke_reason,
            "gate_checks": self.gate_checks,
            "infer_count": self.infer_count,
            "last_activity": self.last_activity,
            "active": self.active,
            "expired": self.expired,
        }

    def record_gate_check(self) -> None:
        self.gate_checks += 1
        self.last_activity = time.time()

    def record_inference(self) -> None:
        self.infer_count += 1
        self.last_activity = time.time()


def create_session(
    surface: str | None = None,
    ttl: int = DEFAULT_SESSION_TTL,
) -> SessionState:
    """Create a new session bound to the current environment authority."""
    grant = cached_authority(surface=surface)
    now = time.time()

    token = _derive_session_token(
        grant.operator_fingerprint,
        grant.surface,
        now,
    )

    session = SessionState(
        token=token,
        operator_fingerprint=grant.operator_fingerprint,
        machine_fingerprint=grant.machine_fingerprint,
        surface=grant.surface,
        grant_status=grant.status,
        seal_status=grant.seal_status,
        capsule_sha256=grant.capsule_sha256,
        entitlements=list(grant.entitlements),
        started_at=now,
        expires_at=now + ttl if grant.valid else 0,
        last_activity=now,
    )

    _persist(session)
    return session


def validate_session(token: str) -> SessionState | None:
    """Load and validate a session by token. Returns None if not found."""
    path = _sessions_dir() / f"{token}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    session = _from_dict(data)
    return session


def revoke_session(
    token: str,
    reason: str = "operator_revoked",
) -> SessionState | None:
    """Revoke a session. Returns the updated session or None if not found."""
    session = validate_session(token)
    if session is None:
        return None

    session.revoked = True
    session.revoked_at = time.time()
    session.revoke_reason = reason
    _persist(session)

    return session


def revoke_all(
    surface: str | None = None,
    reason: str = "bulk_revocation",
) -> int:
    """Revoke all active sessions, optionally filtered by surface."""
    count = 0
    for path in _sessions_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            session = _from_dict(data)
            if session.revoked:
                continue
            if surface and session.surface != surface:
                continue
            session.revoked = True
            session.revoked_at = time.time()
            session.revoke_reason = reason
            _persist(session)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def list_sessions(
    active_only: bool = False,
    surface: str | None = None,
) -> list[SessionState]:
    """List all sessions, optionally filtered."""
    sessions: list[SessionState] = []
    for path in sorted(_sessions_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            session = _from_dict(data)
            if active_only and not session.active:
                continue
            if surface and session.surface != surface:
                continue
            sessions.append(session)
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def cleanup_expired(max_age_seconds: int = 86400) -> int:
    """Remove session files older than max_age_seconds."""
    cutoff = time.time() - max_age_seconds
    count = 0
    for path in _sessions_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            started = data.get("started_at", 0)
            if started < cutoff:
                path.unlink()
                count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def refresh_session(token: str) -> SessionState | None:
    """Re-validate a session against current environment authority.

    If the underlying grant has changed (seal invalidated, capsule
    removed), the session is revoked with reason 'grant_invalidated'.
    """
    session = validate_session(token)
    if session is None:
        return None

    if session.revoked:
        return session

    grant = cached_authority(surface=session.surface)

    if not grant.valid:
        session.revoked = True
        session.revoked_at = time.time()
        session.revoke_reason = "grant_invalidated"
        _persist(session)
        return session

    if grant.operator_fingerprint != session.operator_fingerprint:
        session.revoked = True
        session.revoked_at = time.time()
        session.revoke_reason = "operator_changed"
        _persist(session)
        return session

    session.grant_status = grant.status
    session.seal_status = grant.seal_status
    session.entitlements = list(grant.entitlements)
    _persist(session)
    return session


def _persist(session: SessionState) -> None:
    path = _sessions_dir() / f"{session.token}.json"
    path.write_text(
        json.dumps(session.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _from_dict(data: dict[str, Any]) -> SessionState:
    return SessionState(
        token=data.get("token", ""),
        operator_fingerprint=data.get("operator_fingerprint", ""),
        machine_fingerprint=data.get("machine_fingerprint", ""),
        surface=data.get("surface", ""),
        grant_status=data.get("grant_status", ""),
        seal_status=data.get("seal_status", ""),
        capsule_sha256=data.get("capsule_sha256", ""),
        entitlements=data.get("entitlements", []),
        started_at=data.get("started_at", 0),
        expires_at=data.get("expires_at", 0),
        revoked=data.get("revoked", False),
        revoked_at=data.get("revoked_at", 0),
        revoke_reason=data.get("revoke_reason", ""),
        gate_checks=data.get("gate_checks", 0),
        infer_count=data.get("infer_count", 0),
        last_activity=data.get("last_activity", 0),
    )
