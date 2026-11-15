"""Tests for authority system integrations: policy-gated checks,
session activity tracking, intel-authority correlation, and watchdog."""
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
    entitlements: list[str] | None = None,
    ttl: int = 3600,
) -> AuthorityGrant:
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA,
        status=status,
        operator_fingerprint=operator_fp,
        machine_fingerprint="mach_test",
        capsule_sha256="abc123def456",
        seal_status=seal_status,
        surface=surface,
        entitlements=entitlements or ["transform", "infer", "scan",
                                      "inoculate", "condition", "seal"],
        issued_at=now,
        expires_at=now + ttl if status == "authorized" else 0,
    )


class TestPolicyWiredIntoGates:
    """Verify that check_entitlement consults the policy engine."""

    def test_gate_passes_when_policy_allows(self):
        import authority_gate
        old_audit = authority_gate._audit_enabled
        old_policy = authority_gate._policy_enabled
        authority_gate._audit_enabled = False
        authority_gate._policy_enabled = True
        try:
            from authority_policy import clear_check_history
            clear_check_history()

            grant = _make_grant()
            result = authority_gate.check_entitlement(
                "transform", gate="test", grant=grant,
            )
            assert result.allowed
        finally:
            authority_gate._audit_enabled = old_audit
            authority_gate._policy_enabled = old_policy

    def test_gate_denies_when_policy_denies_compound(self):
        import authority_gate
        old_audit = authority_gate._audit_enabled
        old_policy = authority_gate._policy_enabled
        authority_gate._audit_enabled = False
        authority_gate._policy_enabled = True
        try:
            from authority_policy import (
                PolicyEngine, PolicyRule, clear_check_history, _engine,
            )
            import authority_policy
            clear_check_history()
            saved = authority_policy._engine
            authority_policy._engine = PolicyEngine(rules=[
                PolicyRule(
                    name="infer_requires_scan",
                    rule_type="compound_entitlement",
                    entitlement="infer",
                    config={"requires": ["nonexistent_capability"]},
                ),
            ])
            try:
                grant = _make_grant(entitlements=["infer", "transform"])
                result = authority_gate.check_entitlement(
                    "infer", gate="test", grant=grant,
                )
                assert not result.allowed
                assert "policy:" in result.reason
            finally:
                authority_policy._engine = saved
        finally:
            authority_gate._audit_enabled = old_audit
            authority_gate._policy_enabled = old_policy

    def test_gate_skips_policy_when_disabled(self):
        import authority_gate
        old_audit = authority_gate._audit_enabled
        old_policy = authority_gate._policy_enabled
        authority_gate._audit_enabled = False
        authority_gate._policy_enabled = False
        try:
            grant = _make_grant()
            result = authority_gate.check_entitlement(
                "transform", gate="test", grant=grant,
            )
            assert result.allowed
        finally:
            authority_gate._audit_enabled = old_audit
            authority_gate._policy_enabled = old_policy

    def test_gate_denies_rate_limit(self):
        import authority_gate
        old_audit = authority_gate._audit_enabled
        old_policy = authority_gate._policy_enabled
        authority_gate._audit_enabled = False
        authority_gate._policy_enabled = True
        try:
            from authority_policy import (
                PolicyEngine, PolicyRule, clear_check_history, record_check,
            )
            import authority_policy
            clear_check_history()
            saved = authority_policy._engine
            authority_policy._engine = PolicyEngine(rules=[
                PolicyRule(
                    name="scan_rate_limit",
                    rule_type="rate_limit",
                    entitlement="scan",
                    config={"max_count": 2, "window_seconds": 60},
                ),
            ])
            try:
                grant = _make_grant()
                record_check("scan", grant.surface)
                record_check("scan", grant.surface)
                result = authority_gate.check_entitlement(
                    "scan", gate="test", grant=grant,
                )
                assert not result.allowed
                assert "rate_limit" in result.reason
            finally:
                authority_policy._engine = saved
        finally:
            authority_gate._audit_enabled = old_audit
            authority_gate._policy_enabled = old_policy


class TestSessionActivityTracking:
    """Verify that gate checks record activity to active sessions."""

    def test_gate_notifies_session(self, tmp_path):
        import authority_gate
        old_audit = authority_gate._audit_enabled
        old_policy = authority_gate._policy_enabled
        authority_gate._audit_enabled = False
        authority_gate._policy_enabled = False
        try:
            sessions_dir = tmp_path / "sessions"
            sessions_dir.mkdir()
            grant = _make_grant()
            with patch("session_authority._sessions_dir", return_value=sessions_dir):
                with patch("session_authority.cached_authority", return_value=grant):
                    from session_authority import create_session, validate_session
                    session = create_session()
                    assert session.gate_checks == 0

                    loaded = validate_session(session.token)
                    mock_session_mod = MagicMock()
                    mock_session_mod.list_sessions = MagicMock(return_value=[loaded])
                    mock_session_mod._persist = MagicMock()

                    with patch.dict("sys.modules", {"session_authority": mock_session_mod}):
                        authority_gate.check_entitlement(
                            "transform", gate="test", grant=grant,
                        )
                        assert loaded.gate_checks >= 1
        finally:
            authority_gate._audit_enabled = old_audit
            authority_gate._policy_enabled = old_policy


class TestIntelAuthorityCorrelation:
    """Verify intel events include authority context."""

    def test_intel_event_has_authority_fields(self):
        from provider_intelligence import IntelEvent
        event = IntelEvent(
            timestamp=time.time(),
            provider="test",
            operator_fingerprint="op_123",
            surface="warden_cli",
            session_token="sess_abc",
        )
        d = event.to_dict()
        assert d["operator_fingerprint"] == "op_123"
        assert d["surface"] == "warden_cli"
        assert d["session_token"] == "sess_abc"

    def test_record_interaction_auto_resolves_context(self, tmp_path):
        from provider_intelligence import IntelStore
        store = IntelStore(store_dir=tmp_path / "intel")
        grant = _make_grant()
        with patch("provider_intelligence._resolve_authority_context",
                   return_value=("op_auto", "warden_cli", "sess_auto")):
            event = store.record_interaction(
                provider="anthropic",
                outcome="success",
                quality_score=0.9,
            )
            assert event.operator_fingerprint == "op_auto"
            assert event.surface == "warden_cli"
            assert event.session_token == "sess_auto"[:16]

    def test_record_interaction_explicit_overrides_auto(self, tmp_path):
        from provider_intelligence import IntelStore
        store = IntelStore(store_dir=tmp_path / "intel")
        event = store.record_interaction(
            provider="openai",
            outcome="hedged",
            operator_fingerprint="explicit_op",
            surface="codex_cli",
            session_token="explicit_sess",
        )
        assert event.operator_fingerprint == "explicit_op"
        assert event.surface == "codex_cli"

    def test_from_dict_preserves_new_fields(self):
        from provider_intelligence import IntelEvent
        d = {
            "timestamp": time.time(),
            "provider": "test",
            "operator_fingerprint": "op_x",
            "surface": "generic_cli",
            "session_token": "tok_y",
        }
        event = IntelEvent.from_dict(d)
        assert event.operator_fingerprint == "op_x"
        assert event.surface == "generic_cli"


class TestEnvironmentWatchdog:
    """Verify the watchdog detects environment state changes."""

    def test_clean_environment(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        from env_watchdog import check
                        report = check(auto_invalidate=False, auto_revoke_sessions=False)
                        assert report.clean

    def test_detects_capsule_removal(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("", "missing")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        from env_watchdog import check
                        report = check(auto_invalidate=False, auto_revoke_sessions=False)
                        assert not report.clean
                        types = [c.change_type for c in report.changes]
                        assert "capsule_removed" in types
                        assert report.has_critical

    def test_detects_seal_change(self):
        grant = _make_grant(seal_status="pass")
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="fail"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        from env_watchdog import check
                        report = check(auto_invalidate=False, auto_revoke_sessions=False)
                        types = [c.change_type for c in report.changes]
                        assert "seal_changed" in types

    def test_detects_operator_drift(self):
        grant = _make_grant(operator_fp="original_op")
        drifted = _make_grant(operator_fp="different_op")
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=drifted):
                        from env_watchdog import check
                        report = check(auto_invalidate=False, auto_revoke_sessions=False)
                        types = [c.change_type for c in report.changes]
                        assert "operator_drift" in types

    def test_detects_authorization_loss(self):
        grant = _make_grant(status="authorized")
        lost = _make_grant(status="unauthorized")
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=lost):
                        from env_watchdog import check
                        report = check(auto_invalidate=False, auto_revoke_sessions=False)
                        types = [c.change_type for c in report.changes]
                        assert "authorization_lost" in types

    def test_auto_invalidate_clears_cache(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("", "missing")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        with patch("env_watchdog.invalidate_cache") as mock_inv:
                            from env_watchdog import check
                            report = check(auto_invalidate=True, auto_revoke_sessions=False)
                            assert report.grants_invalidated == 1
                            mock_inv.assert_called_once()

    def test_auto_revoke_sessions_on_critical(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("", "missing")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        with patch("env_watchdog.invalidate_cache"):
                            mock_revoke = MagicMock(return_value=3)
                            with patch.dict("sys.modules", {"session_authority": MagicMock(revoke_all=mock_revoke)}):
                                from env_watchdog import check
                                report = check(auto_invalidate=True, auto_revoke_sessions=True)
                                assert report.sessions_revoked == 3

    def test_report_summary(self):
        from env_watchdog import WatchdogReport, EnvironmentChange
        report = WatchdogReport(
            changes=[
                EnvironmentChange("seal_changed", "pass to fail", "critical", time.time()),
            ],
            grants_invalidated=1,
            sessions_revoked=2,
            checked_at=time.time(),
        )
        s = report.summary()
        assert "1 change(s)" in s
        assert "CRITICAL" in s
        assert "seal_changed" in s

    def test_clean_report_summary(self):
        from env_watchdog import WatchdogReport
        report = WatchdogReport(checked_at=time.time())
        assert "clean" in report.summary().lower()


class TestWatchdogCLI:
    def test_watchdog_cli_runs(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        from bt_cli import main
                        code = main(["watchdog", "--dry-run"])
                        assert code == 0

    def test_watchdog_cli_json(self):
        grant = _make_grant()
        with patch("env_watchdog.cached_authority", return_value=grant):
            with patch("env_watchdog._try_load_capsule", return_value=("abc123def456", "pass")):
                with patch("env_watchdog._try_verify_seal", return_value="pass"):
                    with patch("env_watchdog.resolve_authority", return_value=grant):
                        from bt_cli import main
                        code = main(["--json", "watchdog", "--dry-run"])
                        assert code == 0
