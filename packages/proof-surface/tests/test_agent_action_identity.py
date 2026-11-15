"""The load-bearing differentiator: a receipt is not a trace.

A packet's identity (packet_id) is the durable receipt; spans and traces are
evidence. The validator rejects any attempt to substitute a span id or the trace
id for the receipt identity.
"""

from __future__ import annotations

from proof_surface.agent_action import (
    build_agent_action_packet,
    validate_agent_action_packet,
)

_HEX = "a" * 64
_HEX2 = "c" * 64

_AUTH = {
    "authorization_version": "0.1",
    "receipt_id": "auth-1",
    "kind": "authorization-grant",
    "principal": {"id": "user:zain"},
    "agent": {"id": "agent:claude"},
    "intent": "write",
    "scope": {
        "allowed_actions": ["fs.write"],
        "allowed_targets": ["/work/config.json"],
    },
    "granted_at": "2020-01-01T00:00:00+00:00",
    "expires_at": "2999-01-01T00:00:00+00:00",
    "revoked": False,
}


def _trace():
    return {
        "trace_id": "trace-xyz",
        "service": "demo",
        "spans": [
            {
                "span_id": "span-s2",
                "parent_span_id": None,
                "name": "write",
                "kind": "client",
                "start_unix_ns": 0,
                "end_unix_ns": 1,
                "status": {"code": "ok", "message": ""},
                "attributes": {
                    "actor.id": "user:zain",
                    "tool.name": "fs",
                    "action.kind": "fs.write",
                    "action.target": "/work/config.json",
                    "side_effect.class": "write",
                    "content.sha256": _HEX,
                    "after.sha256": _HEX2,
                },
                "events": [],
            }
        ],
    }


def _packet(packet_id):
    return build_agent_action_packet(
        _trace(), _AUTH, claim="c", scope="s", packet_id=packet_id
    )


def test_normal_receipt_identity_validates_and_differs_from_trace():
    packet = _packet("pkt-1")
    assert validate_agent_action_packet(packet) == []
    assert packet["packet_id"] == "pkt-1"
    assert packet["packet_id"] != _trace()["trace_id"]
    # the trace appears only as evidence, under sources
    assert packet["sources"][0]["ref"] == "trace:trace-xyz"


def test_receipt_identity_may_not_be_a_span_id():
    packet = _packet("span-s2")  # substitute a span id for the receipt identity
    issues = validate_agent_action_packet(packet)
    assert any("packet_id" in i.path for i in issues)


def test_receipt_identity_may_not_be_the_trace_id():
    packet = _packet("trace-xyz")  # substitute the trace id for the receipt identity
    issues = validate_agent_action_packet(packet)
    assert any("packet_id" in i.path for i in issues)
