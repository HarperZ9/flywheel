"""Tests for the governance envelope (cross-lane state carrier)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from harness.governance_envelope import (
    SCHEMA,
    GovernanceEnvelope,
    build_envelope,
)

COMPLETE = {
    "required": 1, "measured": 1, "present": 1,
    "absent": 0, "unknown": 0, "compliant": True,
}
CLASSIFICATION_REF = "a" * 64


def test_envelope_has_schema():
    env = GovernanceEnvelope()
    d = env.to_dict()
    assert d["schema"] == SCHEMA


def test_default_envelope_is_paused_without_evidence():
    env = GovernanceEnvelope()
    assert env.tier == "T1"
    assert env.governance_verdict == "pause"


def test_envelope_fingerprint_stable():
    env1 = GovernanceEnvelope(tier="T2", modifiers=["A"])
    env2 = GovernanceEnvelope(tier="T2", modifiers=["A"])
    assert env1.fingerprint() == env2.fingerprint()


def test_envelope_fingerprint_changes_with_tier():
    env1 = GovernanceEnvelope(tier="T1")
    env2 = GovernanceEnvelope(tier="T3")
    assert env1.fingerprint() != env2.fingerprint()


def test_allows_action_within_tier():
    env = GovernanceEnvelope(
        tier="T3", governance_verdict="allow",
        control_compliance=COMPLETE, classification_ref=CLASSIFICATION_REF)
    assert env.allows_action("T1") is True
    assert env.allows_action("T2") is True
    assert env.allows_action("T3") is True


def test_blocks_action_above_tier():
    env = GovernanceEnvelope(
        tier="T1", governance_verdict="allow",
        control_compliance=COMPLETE, classification_ref=CLASSIFICATION_REF)
    assert env.allows_action("T1") is True
    assert env.allows_action("T2") is False
    assert env.allows_action("T3") is False


def test_unknown_action_tier_never_authorizes():
    env = GovernanceEnvelope(
        tier="T3", governance_verdict="allow",
        control_compliance=COMPLETE, classification_ref=CLASSIFICATION_REF)
    assert env.allows_action("T9") is False
    assert env.allows_action("") is False


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
        compliance_report={"required": 14, "measured": 14, "present": 14,
                           "absent": 0, "unknown": 0, "compliant": True},
        classification_ref="a" * 64)
    assert env.governance_verdict == "allow"
    assert env.control_compliance["present"] == 14


def test_build_envelope_non_compliant_t1_pauses():
    env = build_envelope(
        tier="T1",
        compliance_report={"required": 14, "measured": 14, "present": 11,
                           "absent": 3, "unknown": 0, "compliant": False})
    assert env.governance_verdict == "pause"


def test_build_envelope_non_compliant_t3_denies():
    env = build_envelope(
        tier="T3",
        compliance_report={"required": 52, "measured": 52, "present": 51,
                           "absent": 1, "unknown": 0, "compliant": False})
    assert env.governance_verdict == "deny"


def test_envelope_carries_pause_triggers():
    env = build_envelope(
        tier="T2",
        compliance_report={"required": 32, "measured": 32, "present": 32,
                           "absent": 0, "unknown": 0, "compliant": True},
        pause_triggers=["capability-increase", "safeguard-bypass"])
    assert len(env.pause_triggers) == 2


def test_envelope_carries_modifiers():
    env = build_envelope(
        tier="T2",
        compliance_report={"required": 32, "measured": 32, "present": 32,
                           "absent": 0, "unknown": 0, "compliant": True},
        modifiers=["A", "D"])
    d = env.to_dict()
    assert "A" in d["modifiers"]
    assert "D" in d["modifiers"]


def test_missing_compliance_pauses():
    env = build_envelope(tier="T1", compliance_report=None,
                         classification_ref="a" * 64)
    assert env.governance_verdict == "pause"


def test_incomplete_or_unknown_compliance_pauses():
    env = build_envelope(
        tier="T1",
        compliance_report={"required": 14, "measured": 13, "present": 13,
                           "absent": 0, "unknown": 1, "compliant": False},
        classification_ref="a" * 64)
    assert env.governance_verdict == "pause"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tier": "T9"},
        {"modifiers": ["Z"]},
        {"governance_verdict": "maybe"},
    ],
)
def test_envelope_rejects_open_governance_values(kwargs):
    with pytest.raises(ValueError):
        GovernanceEnvelope(**kwargs)


def test_fingerprint_binds_every_decision_field():
    base = GovernanceEnvelope(
        tier="T2", modifiers=["A"],
        control_compliance={"required": 1, "measured": 1, "present": 1,
                            "absent": 0, "unknown": 0, "compliant": True},
        pause_triggers=["capability-increase"],
        authorization_receipt_ref="b" * 64,
        risk_signals=[{"kind": "observation", "ref": "signal://1"}],
        classification_ref="a" * 64, governance_verdict="allow",
        timestamp="2026-08-02T00:00:00Z")
    mutations = [
        {"tier": "T3"}, {"modifiers": ["D"]},
        {"control_compliance": {"required": 1, "measured": 0,
                                "present": 0, "absent": 0, "unknown": 1,
                                "compliant": False}},
        {"pause_triggers": ["new"]},
        {"authorization_receipt_ref": "c" * 64},
        {"risk_signals": [{"kind": "assessment", "ref": "signal://1"}]},
        {"classification_ref": "d" * 64},
        {"governance_verdict": "pause"},
        {"timestamp": "2026-08-02T00:00:01Z"},
    ]
    assert all(replace(base, **change).fingerprint() != base.fingerprint()
               for change in mutations)
