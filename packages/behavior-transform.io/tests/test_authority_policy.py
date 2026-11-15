"""Tests for the authority policy engine."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from env_authority import AuthorityGrant

SCHEMA = "behavior-transform.env-authority.v1"


def _make_grant(
    surface: str = "warden_cli",
    entitlements: list[str] | None = None,
) -> AuthorityGrant:
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="op_test",
        machine_fingerprint="mach_test",
        capsule_sha256="abc123",
        seal_status="pass",
        surface=surface,
        entitlements=entitlements or ["transform", "infer", "scan",
                                      "inoculate", "condition", "seal"],
        issued_at=now,
        expires_at=now + 3600,
    )


def _make_limited_grant(
    surface: str = "generic_cli",
    entitlements: list[str] | None = None,
) -> AuthorityGrant:
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="op_test",
        machine_fingerprint="mach_test",
        capsule_sha256="abc123",
        seal_status="pass",
        surface=surface,
        entitlements=entitlements or ["transform", "scan"],
        issued_at=now,
        expires_at=now + 3600,
    )


class TestCompoundEntitlement:
    def test_inoculate_allowed_with_transform(self):
        from authority_policy import PolicyEngine, PolicyRule
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="inoculate_requires_transform",
                rule_type="compound_entitlement",
                entitlement="inoculate",
                config={"requires": ["transform"]},
            ),
        ])
        grant = _make_grant()
        verdict = engine.evaluate("inoculate", grant)
        assert verdict.allowed

    def test_inoculate_denied_without_transform(self):
        from authority_policy import PolicyEngine, PolicyRule
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="inoculate_requires_transform",
                rule_type="compound_entitlement",
                entitlement="inoculate",
                config={"requires": ["transform"]},
            ),
        ])
        grant = _make_limited_grant(entitlements=["inoculate"])
        verdict = engine.evaluate("inoculate", grant)
        assert not verdict.allowed
        assert "compound" in verdict.denial_reason

    def test_no_rules_for_entitlement_passes(self):
        from authority_policy import PolicyEngine
        engine = PolicyEngine(rules=[])
        grant = _make_grant()
        verdict = engine.evaluate("transform", grant)
        assert verdict.allowed
        assert verdict.rules_evaluated == 0


class TestRateLimit:
    def test_within_limit_passes(self):
        from authority_policy import (
            PolicyEngine, PolicyRule, clear_check_history, record_check,
        )
        clear_check_history()
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_rate_limit",
                rule_type="rate_limit",
                entitlement="infer",
                config={"max_count": 5, "window_seconds": 60},
            ),
        ])
        grant = _make_grant()
        record_check("infer", grant.surface)
        record_check("infer", grant.surface)
        verdict = engine.evaluate("infer", grant)
        assert verdict.allowed

    def test_exceeds_limit_denied(self):
        from authority_policy import (
            PolicyEngine, PolicyRule, clear_check_history, record_check,
        )
        clear_check_history()
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_rate_limit",
                rule_type="rate_limit",
                entitlement="infer",
                config={"max_count": 3, "window_seconds": 60},
            ),
        ])
        grant = _make_grant()
        for _ in range(3):
            record_check("infer", grant.surface)
        verdict = engine.evaluate("infer", grant)
        assert not verdict.allowed
        assert "rate_limit" in verdict.denial_reason


class TestCooldown:
    def test_cooldown_passes_after_interval(self):
        from authority_policy import (
            PolicyEngine, PolicyRule, clear_check_history, record_check,
        )
        clear_check_history()
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_cooldown",
                rule_type="cooldown",
                entitlement="infer",
                config={"min_interval_seconds": 0.01},
            ),
        ])
        grant = _make_grant()
        record_check("infer", grant.surface)
        time.sleep(0.02)
        verdict = engine.evaluate("infer", grant)
        assert verdict.allowed

    def test_cooldown_denied_too_fast(self):
        from authority_policy import (
            PolicyEngine, PolicyRule, clear_check_history, record_check,
        )
        clear_check_history()
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_cooldown",
                rule_type="cooldown",
                entitlement="infer",
                config={"min_interval_seconds": 10},
            ),
        ])
        grant = _make_grant()
        record_check("infer", grant.surface)
        verdict = engine.evaluate("infer", grant)
        assert not verdict.allowed
        assert "cooldown" in verdict.denial_reason


class TestSessionRequired:
    def test_denied_without_active_session(self):
        from authority_policy import PolicyEngine, PolicyRule
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_needs_session",
                rule_type="session_required",
                entitlement="infer",
            ),
        ])
        grant = _make_grant()
        mock_mod = MagicMock()
        mock_mod.list_sessions = MagicMock(return_value=[])
        with patch.dict("sys.modules", {"session_authority": mock_mod}):
            verdict = engine.evaluate("infer", grant)
            assert not verdict.allowed
            assert "session_required" in verdict.denial_reason

    def test_allowed_with_active_session(self):
        from authority_policy import PolicyEngine, PolicyRule
        engine = PolicyEngine(rules=[
            PolicyRule(
                name="infer_needs_session",
                rule_type="session_required",
                entitlement="infer",
            ),
        ])
        grant = _make_grant()
        mock_session = type("S", (), {"active": True})()
        mock_mod = MagicMock()
        mock_mod.list_sessions = MagicMock(return_value=[mock_session])
        with patch.dict("sys.modules", {"session_authority": mock_mod}):
            verdict = engine.evaluate("infer", grant)
            assert verdict.allowed


class TestDefaultPolicies:
    def test_default_policies_load(self):
        from authority_policy import DEFAULT_POLICIES
        assert len(DEFAULT_POLICIES) >= 3
        names = [r.name for r in DEFAULT_POLICIES]
        assert "inoculate_requires_transform" in names
        assert "infer_rate_limit" in names

    def test_default_engine_evaluates(self):
        from authority_policy import PolicyEngine, clear_check_history
        clear_check_history()
        engine = PolicyEngine()
        grant = _make_grant()
        verdict = engine.evaluate("inoculate", grant)
        assert verdict.allowed


class TestPolicyVerdict:
    def test_to_dict(self):
        from authority_policy import PolicyVerdict
        v = PolicyVerdict(
            allowed=False,
            entitlement="infer",
            rules_evaluated=3,
            rules_passed=1,
            denial_rule="rate_limit",
            denial_reason="too fast",
        )
        d = v.to_dict()
        assert d["allowed"] is False
        assert d["denial_rule"] == "rate_limit"


class TestPolicyCLI:
    def test_policy_list_cli(self):
        from bt_cli import main
        code = main(["policy", "list"])
        assert code == 0

    def test_policy_check_cli(self):
        from authority_policy import clear_check_history
        clear_check_history()
        from bt_cli import main
        code = main(["--json", "policy", "check", "--entitlement", "transform"])
        assert code == 0
