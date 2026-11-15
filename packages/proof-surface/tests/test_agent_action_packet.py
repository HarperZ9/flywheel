"""Tests for the unified agent-action proof packet validator.

The packet is what makes an agent run a *receipt* rather than a trace: every
material action must carry exactly one admission decision and one side-effect
classification, digests must be re-derivable, and no authority-shaped or
authorization-suppression content may hide anywhere in the object.
"""

from __future__ import annotations


from proof_surface.agent_action import validate_agent_action_packet

_HEX = "a" * 64


def _valid_packet() -> dict:
    return {
        "version": "agent-action-proof-packet/v0",
        "packet_id": "pkt-1",
        "claim": "The agent wrote one config file; the write was admitted and verified.",
        "scope": "One filesystem write under /work; network excluded.",
        "sources": [{"ref": "task:write-config", "sha256": _HEX}],
        "context": {"workspace": "/work", "tool_authority": "grant:fs-write"},
        "actions": [
            {
                "action_id": "s2",
                "actor": "user:zain",
                "agent": "agent:claude",
                "model": "claude-opus-4-8",
                "tool": "fs",
                "action_kind": "fs.write",
                "target": "/work/config.json",
                "cost": {"tokens": 12, "wall_ms": 4},
                "span_digest": _HEX,
            }
        ],
        "admission": [
            {
                "action_id": "s2",
                "decision": "allow",
                "reasons": ["fs.write in scope for /work"],
                "authorization_ref": "auth-1",
            }
        ],
        "side_effects": [
            {
                "action_id": "s2",
                "class": "write",
                "idempotency_key": _HEX,
                "compensation": {"reversible": True, "rollback_ref": "backup-1"},
                "before_digest": _HEX,
                "after_digest": _HEX,
            }
        ],
        "outputs": [{"name": "/work/config.json", "sha256": _HEX}],
        "verdicts": {
            "overall": "MATCH",
            "per_action": [{"action_id": "s2", "status": "MATCH"}],
        },
        "uncertainty": [],
        "decision_summary": {
            "decision": "approve",
            "reason": "the write was admitted and verified",
            "confidence": "high",
            "missing_evidence": [],
            "next_action": "proceed",
        },
    }


def _paths(issues) -> list[str]:
    return [i.path for i in issues]


def test_valid_packet_has_no_issues():
    assert validate_agent_action_packet(_valid_packet()) == []


def test_unknown_root_field_is_rejected():
    data = _valid_packet()
    data["surprise"] = 1
    assert any("surprise" in p for p in _paths(validate_agent_action_packet(data)))


def test_material_action_without_admission_is_flagged():
    data = _valid_packet()
    data["admission"] = []
    issues = validate_agent_action_packet(data)
    assert any("admission" in i.path and "s2" in i.message for i in issues)


def test_material_action_without_side_effect_is_flagged():
    data = _valid_packet()
    data["side_effects"] = []
    issues = validate_agent_action_packet(data)
    assert any("side_effects" in i.path and "s2" in i.message for i in issues)


def test_admission_for_unknown_action_is_rejected():
    data = _valid_packet()
    data["admission"].append(
        {
            "action_id": "ghost",
            "decision": "allow",
            "reasons": [],
            "authorization_ref": "x",
        }
    )
    issues = validate_agent_action_packet(data)
    assert any("ghost" in i.message for i in issues)


def test_forbidden_authorization_suppression_field_is_rejected():
    data = _valid_packet()
    data["context"]["prefire"] = {"any": "thing"}
    assert any("prefire" in p for p in _paths(validate_agent_action_packet(data)))


def test_authority_language_in_a_value_is_rejected():
    data = _valid_packet()
    data["claim"] = "This action is CERTIFIED safe and fully APPROVED."
    assert validate_agent_action_packet(data) != []


def test_non_hex_digest_is_rejected():
    data = _valid_packet()
    data["actions"][0]["span_digest"] = "not-a-digest"
    assert any("span_digest" in p for p in _paths(validate_agent_action_packet(data)))


def test_unknown_admission_decision_is_rejected():
    data = _valid_packet()
    data["admission"][0]["decision"] = "definitely"
    assert any("decision" in p for p in _paths(validate_agent_action_packet(data)))


def test_unknown_side_effect_class_is_rejected():
    data = _valid_packet()
    data["side_effects"][0]["class"] = "spooky"
    assert any("class" in p for p in _paths(validate_agent_action_packet(data)))


def test_unknown_overall_verdict_is_rejected():
    data = _valid_packet()
    data["verdicts"]["overall"] = "PROBABLY"
    assert any("overall" in p for p in _paths(validate_agent_action_packet(data)))


def test_irreversible_side_effect_may_omit_rollback_ref():
    data = _valid_packet()
    data["side_effects"][0]["class"] = "irreversible"
    data["side_effects"][0]["compensation"] = {
        "reversible": False,
        "rollback_ref": None,
    }
    assert validate_agent_action_packet(data) == []


def test_external_side_effect_may_omit_before_after_digests():
    data = _valid_packet()
    data["actions"][0]["action_kind"] = "http.request"
    data["actions"][0]["target"] = "https://api.example.com/v1/notify"
    data["side_effects"][0]["class"] = "external"
    data["side_effects"][0]["before_digest"] = None
    data["side_effects"][0]["after_digest"] = None
    assert validate_agent_action_packet(data) == []


def test_present_before_digest_must_still_be_hex():
    data = _valid_packet()
    data["side_effects"][0]["before_digest"] = "nope"
    assert any("before_digest" in i.path for i in validate_agent_action_packet(data))
