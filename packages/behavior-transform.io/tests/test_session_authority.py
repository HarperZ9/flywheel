"""Tests for session authority binding and lifecycle."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from env_authority import AuthorityGrant

SCHEMA = "behavior-transform.env-authority.v1"


def _make_grant(
    status: str = "authorized",
    seal_status: str = "pass",
    surface: str = "warden_cli",
    operator_fp: str = "op_test_fp_123456",
    machine_fp: str = "mach_test_fp",
    capsule_sha: str = "abc123def456",
    entitlements: list[str] | None = None,
    ttl: int = 3600,
) -> AuthorityGrant:
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA,
        status=status,
        operator_fingerprint=operator_fp,
        machine_fingerprint=machine_fp,
        capsule_sha256=capsule_sha,
        seal_status=seal_status,
        surface=surface,
        entitlements=entitlements or ["transform", "infer", "scan"],
        issued_at=now,
        expires_at=now + ttl if status == "authorized" else 0,
    )


@pytest.fixture
def sessions_dir(tmp_path):
    d = tmp_path / "sessions"
    d.mkdir()
    with patch("session_authority._sessions_dir", return_value=d):
        yield d


@pytest.fixture
def mock_grant():
    grant = _make_grant()
    with patch("session_authority.cached_authority", return_value=grant):
        yield grant


class TestCreateSession:
    def test_creates_active_session(self, sessions_dir, mock_grant):
        from session_authority import create_session
        session = create_session(surface="warden_cli")
        assert session.active
        assert session.token
        assert len(session.token) == 32
        assert session.surface == "warden_cli"
        assert session.operator_fingerprint == mock_grant.operator_fingerprint

    def test_persists_to_disk(self, sessions_dir, mock_grant):
        from session_authority import create_session
        session = create_session()
        path = sessions_dir / f"{session.token}.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["token"] == session.token

    def test_unauthorized_grant_produces_inactive_session(self, sessions_dir):
        bad_grant = _make_grant(status="unauthorized")
        with patch("session_authority.cached_authority", return_value=bad_grant):
            from session_authority import create_session
            session = create_session()
            assert not session.active
            assert session.expires_at == 0

    def test_unique_tokens_per_call(self, sessions_dir, mock_grant):
        from session_authority import create_session
        s1 = create_session()
        time.sleep(0.01)
        s2 = create_session()
        assert s1.token != s2.token


class TestValidateSession:
    def test_validates_existing(self, sessions_dir, mock_grant):
        from session_authority import create_session, validate_session
        session = create_session()
        loaded = validate_session(session.token)
        assert loaded is not None
        assert loaded.token == session.token

    def test_returns_none_for_missing(self, sessions_dir):
        from session_authority import validate_session
        assert validate_session("nonexistent_token_value_here") is None


class TestRevokeSession:
    def test_revokes(self, sessions_dir, mock_grant):
        from session_authority import create_session, revoke_session
        session = create_session()
        assert session.active
        revoked = revoke_session(session.token, reason="test_revoke")
        assert revoked is not None
        assert revoked.revoked
        assert revoked.revoke_reason == "test_revoke"
        assert not revoked.active

    def test_revoke_missing_returns_none(self, sessions_dir):
        from session_authority import revoke_session
        assert revoke_session("no_such_token_exists_here") is None


class TestRevokeAll:
    def test_revokes_all(self, sessions_dir, mock_grant):
        from session_authority import create_session, revoke_all, list_sessions
        for _ in range(3):
            create_session()
            time.sleep(0.01)
        count = revoke_all()
        assert count == 3
        active = list_sessions(active_only=True)
        assert len(active) == 0

    def test_revokes_filtered_by_surface(self, sessions_dir, mock_grant):
        from session_authority import create_session, revoke_all, list_sessions
        create_session(surface="warden_cli")
        time.sleep(0.01)
        count = revoke_all(surface="other_surface")
        assert count == 0


class TestRefreshSession:
    def test_refresh_revokes_on_invalid_grant(self, sessions_dir, mock_grant):
        from session_authority import create_session, refresh_session
        session = create_session()
        bad_grant = _make_grant(status="unauthorized")
        with patch("session_authority.cached_authority", return_value=bad_grant):
            refreshed = refresh_session(session.token)
            assert refreshed is not None
            assert refreshed.revoked
            assert refreshed.revoke_reason == "grant_invalidated"

    def test_refresh_revokes_on_operator_change(self, sessions_dir, mock_grant):
        from session_authority import create_session, refresh_session
        session = create_session()
        new_grant = _make_grant(operator_fp="different_operator_fp")
        with patch("session_authority.cached_authority", return_value=new_grant):
            refreshed = refresh_session(session.token)
            assert refreshed.revoked
            assert refreshed.revoke_reason == "operator_changed"

    def test_refresh_updates_entitlements(self, sessions_dir, mock_grant):
        from session_authority import create_session, refresh_session
        session = create_session()
        updated_grant = _make_grant(entitlements=["transform", "infer", "scan", "seal"])
        with patch("session_authority.cached_authority", return_value=updated_grant):
            refreshed = refresh_session(session.token)
            assert refreshed.active
            assert "seal" in refreshed.entitlements


class TestListSessions:
    def test_lists_all(self, sessions_dir, mock_grant):
        from session_authority import create_session, list_sessions
        for _ in range(3):
            create_session()
            time.sleep(0.01)
        sessions = list_sessions()
        assert len(sessions) == 3

    def test_filters_active(self, sessions_dir, mock_grant):
        from session_authority import create_session, revoke_session, list_sessions
        s1 = create_session()
        time.sleep(0.01)
        s2 = create_session()
        revoke_session(s1.token)
        active = list_sessions(active_only=True)
        assert len(active) == 1
        assert active[0].token == s2.token


class TestCleanup:
    def test_removes_old_sessions(self, sessions_dir, mock_grant):
        from session_authority import create_session, cleanup_expired
        session = create_session()
        path = sessions_dir / f"{session.token}.json"
        data = json.loads(path.read_text())
        data["started_at"] = time.time() - 100000
        path.write_text(json.dumps(data))
        count = cleanup_expired(max_age_seconds=86400)
        assert count == 1
        assert not path.exists()


class TestSessionActivity:
    def test_record_gate_check(self, sessions_dir, mock_grant):
        from session_authority import create_session
        session = create_session()
        session.record_gate_check()
        session.record_gate_check()
        assert session.gate_checks == 2
        assert session.last_activity > 0

    def test_record_inference(self, sessions_dir, mock_grant):
        from session_authority import create_session
        session = create_session()
        session.record_inference()
        assert session.infer_count == 1


class TestSessionCLI:
    def test_session_create_cli(self, sessions_dir, mock_grant):
        from bt_cli import main
        code = main(["--json", "session", "create", "--surface", "warden_cli"])
        assert code == 0

    def test_session_list_cli(self, sessions_dir, mock_grant):
        from bt_cli import main
        main(["session", "create"])
        code = main(["session", "list"])
        assert code == 0
