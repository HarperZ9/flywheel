"""Tests for the governance envelope (cross-lane state carrier)."""
from __future__ import annotations

from harness.governance_envelope import (
    SCHEMA,
    GovernanceEnvelope,
    build_envelope,
)


def test_envelope_has_schema():
    env = GovernanceEnvelope()
    d = env.to_dict()
    assert d["schema"] == SCHEMA


def test_default_envelope_is_t1_allow():
    env = GovernanceEnvelope()
    assert env.tier == "T1"
    assert env.governance_verdict == "allow"


def test_envelope_fingerprint_stable():
    env1 = GovernanceEnvelope(tier="T2", modifiers=["A"])
    env2 = GovernanceEnvelope(tier="T2", modifiers=["A"])
    assert env1.fingerprint() == env2.fingerprint()


def test_envelope_fingerprint_changes_with_tier():
    env1 = GovernanceEnvelope(tier="T1")
    env2 = GovernanceEnvelope(tier="T3")
    assert env1.fingerprint() != env2.fingerprint()


def test_allows_action_within_tier():
    env = GovernanceEnvelope(tier="T3", governance_verdict="allow")
    assert env.allows_action("T1") is True
    assert env.allows_action("T2") is True
    assert env.allows_action("T3") is True


def test_blocks_action_above_tier():
    env = GovernanceEnvelope(tier="T1", governance_verdict="allow")
    assert env.allows_action("T1") is True
    assert env.allows_action("T2") is False
    assert env.allows_action("T3") is False


def test_paused_envelope_blocks_all():
    env = GovernanceEnvelope(tier="T3", governance_verdict="pause")
    assert env.allows_action("T1") is False
    assert env.allows_action("T3") is False


def test_denied_envelope_blocks_all():
    env = GovernanceEnvelope(tier="T3", governance_verdict="deny")
    assert env.allows_action("T1") is False


def test_build_envelope_compliant():
    env = build_envelope(
        tier="T1",
        compliance_report={"failed": 0, "passed": 14, "checked": 14},
        classification_ref="abc123")
    assert env.governance_verdict == "allow"
    assert env.control_compliance["passed"] == 14


def test_build_envelope_non_compliant_t1_pauses():
    env = build_envelope(
        tier="T1",
        compliance_report={"failed": 3, "passed": 11, "checked": 14})
    assert env.governance_verdict == "pause"


def test_build_envelope_non_compliant_t3_denies():
    env = build_envelope(
        tier="T3",
        compliance_report={"failed": 1, "passed": 51, "checked": 52})
    assert env.governance_verdict == "deny"


def test_envelope_carries_pause_triggers():
    env = build_envelope(
        tier="T2",
        compliance_report={"failed": 0, "passed": 32, "checked": 32},
        pause_triggers=["capability-increase", "safeguard-bypass"])
    assert len(env.pause_triggers) == 2


def test_envelope_carries_modifiers():
    env = build_envelope(
        tier="T2-A/D",
        compliance_report={"failed": 0, "passed": 1, "checked": 1},
        modifiers=["A", "D"])
    d = env.to_dict()
    assert "A" in d["modifiers"]
    assert "D" in d["modifiers"]
