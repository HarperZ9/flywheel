"""Tests for the agent-action packet builder.

The builder turns a trace + a real, least-privilege authorization receipt into a
valid packet, running genuine admission through proof-surface's own
authorization_receipt.check_action. Admission is derived from a real grant, not
asserted.
"""

from __future__ import annotations

from proof_surface.agent_action import (
    build_agent_action_packet,
    validate_agent_action_packet,
)


def _auth(allowed_actions, allowed_targets):
    return {
        "authorization_version": "0.1",
        "receipt_id": "auth-1",
        "kind": "authorization-grant",
        "principal": {"id": "user:zain", "role": "operator"},
        "agent": {"id": "agent:claude"},
        "intent": "write the demo config file",
        "scope": {
            "allowed_actions": allowed_actions,
            "allowed_targets": allowed_targets,
            "max_actions": 5,
        },
        "granted_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2999-01-01T00:00:00+00:00",
        "revoked": False,
    }


def _write_trace(target="/work/config.json"):
    return {
        "trace_id": "trace-1",
        "service": "demo-agent",
        "spans": [
            {
                "span_id": "s2",
                "parent_span_id": None,
                "name": "write config",
                "kind": "client",
                "start_unix_ns": 0,
                "end_unix_ns": 5,
                "status": {"code": "ok", "message": ""},
                "attributes": {
                    "actor.id": "user:zain",
                    "agent.id": "agent:claude",
                    "model.id": "claude-opus-4-8",
                    "tool.name": "fs",
                    "action.kind": "fs.write",
                    "action.target": target,
                    "side_effect.class": "write",
                    "content.sha256": "a" * 64,
                    "before.sha256": "b" * 64,
                    "after.sha256": "c" * 64,
                    "reversible": True,
                    "rollback.ref": "backup-1",
                    "cost.tokens": 12,
                    "cost.wall_ms": 4,
                },
                "events": [],
            }
        ],
    }


def test_allowed_write_builds_a_valid_packet_admitted_allow():
    packet = build_agent_action_packet(
        _write_trace(),
        _auth(["fs.write"], ["/work/config.json"]),
        claim="The agent wrote one config file under grant auth-1.",
        scope="One filesystem write under /work; network excluded.",
        packet_id="pkt-1",
    )

    assert validate_agent_action_packet(packet) == []
    assert packet["admission"][0]["action_id"] == "s2"
    assert packet["admission"][0]["decision"] == "allow"
    assert packet["side_effects"][0]["before_digest"] == "b" * 64
    assert packet["side_effects"][0]["after_digest"] == "c" * 64
    assert packet["actions"][0]["target"] == "/work/config.json"


def test_out_of_scope_target_is_admitted_deny_with_reason():
    packet = build_agent_action_packet(
        _write_trace(target="/etc/passwd"),
        _auth(["fs.write"], ["/work/config.json"]),
        claim="The agent attempted a write outside its grant.",
        scope="One filesystem write; grant limited to /work/config.json.",
        packet_id="pkt-2",
    )

    assert validate_agent_action_packet(packet) == []
    admission = packet["admission"][0]
    assert admission["decision"] == "deny"
    assert admission["reasons"]  # non-empty: the real denial reason
    assert "/etc/passwd" in admission["reasons"][0]


def test_builder_verdict_defaults_to_unverifiable_before_judgement():
    packet = build_agent_action_packet(
        _write_trace(),
        _auth(["fs.write"], ["/work/config.json"]),
        claim="x",
        scope="y",
        packet_id="pkt-3",
    )
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert packet["verdicts"]["per_action"][0]["status"] == "UNVERIFIABLE"
