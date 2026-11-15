"""Tests for the crucible verdict bridge.

attach_verdicts() fills the packet's verdict layer from admission + effect
evidence using an embedded verdict_for that is faithful to crucible's pure
semantics (margin = (tolerance - deviation)/tolerance; fail-closed to
UNVERIFIABLE). to_crucible_inputs() emits crucible's exact thesis/measurements
file contract so real crucible can independently re-derive the same verdict.
"""

from __future__ import annotations

from proof_surface.agent_action import (
    attach_verdicts,
    build_agent_action_packet,
    to_crucible_inputs,
    validate_agent_action_packet,
    verdict_for_measurement,
)


def _auth(actions, targets):
    return {
        "authorization_version": "0.1",
        "receipt_id": "auth-1",
        "kind": "authorization-grant",
        "principal": {"id": "user:zain"},
        "agent": {"id": "agent:claude"},
        "intent": "demo",
        "scope": {"allowed_actions": actions, "allowed_targets": targets},
        "granted_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2999-01-01T00:00:00+00:00",
        "revoked": False,
    }


def _span(attributes):
    return {
        "span_id": "s2",
        "parent_span_id": None,
        "name": "act",
        "kind": "client",
        "start_unix_ns": 0,
        "end_unix_ns": 1,
        "status": {"code": "ok", "message": ""},
        "attributes": attributes,
        "events": [],
    }


def _write_attrs(target="/work/config.json"):
    return {
        "actor.id": "user:zain",
        "tool.name": "fs",
        "action.kind": "fs.write",
        "action.target": target,
        "side_effect.class": "write",
        "content.sha256": "a" * 64,
        "before.sha256": "b" * 64,
        "after.sha256": "c" * 64,
        "reversible": True,
        "rollback.ref": "backup-1",
    }


def _external_attrs():
    return {
        "actor.id": "user:zain",
        "tool.name": "http",
        "action.kind": "http.request",
        "action.target": "https://api.example.com/notify",
        "side_effect.class": "external",
        "content.sha256": "d" * 64,
    }


def _packet(attrs, auth):
    trace = {"trace_id": "t1", "service": "agent", "spans": [_span(attrs)]}
    return build_agent_action_packet(trace, auth, claim="c", scope="s", packet_id="pkt")


def test_allowed_and_verified_action_is_match():
    packet = attach_verdicts(
        _packet(_write_attrs(), _auth(["fs.write"], ["/work/config.json"]))
    )
    assert packet["verdicts"]["per_action"][0]["status"] == "MATCH"
    assert packet["verdicts"]["overall"] == "MATCH"
    assert validate_agent_action_packet(packet) == []


def test_denied_action_is_drift():
    packet = attach_verdicts(
        _packet(_write_attrs("/etc/passwd"), _auth(["fs.write"], ["/work/config.json"]))
    )
    assert packet["verdicts"]["per_action"][0]["status"] == "DRIFT"
    assert packet["verdicts"]["overall"] == "DRIFT"
    assert validate_agent_action_packet(packet) == []


def test_unobserved_effect_is_unverifiable():
    # Allowed external call, but no after-state digest -> cannot be verified.
    packet = attach_verdicts(
        _packet(
            _external_attrs(),
            _auth(["http.request"], ["https://api.example.com/notify"]),
        )
    )
    assert packet["verdicts"]["per_action"][0]["status"] == "UNVERIFIABLE"
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert validate_agent_action_packet(packet) == []


def test_to_crucible_inputs_shape_is_the_documented_contract():
    packet = attach_verdicts(
        _packet(_write_attrs(), _auth(["fs.write"], ["/work/config.json"]))
    )
    thesis, measurements = to_crucible_inputs(packet)

    assert thesis["disposition"] == "publishable"
    assert thesis["title"]
    claim = thesis["claims"][0]
    assert claim["text"]
    assert claim["falsification"]  # every claim must carry a falsifier
    row = measurements["measurements"][0]
    assert row["claim"] == claim["text"]  # binds by exact text
    assert row["tolerance"] > 0
    assert isinstance(row["deviation"], (int, float))
    assert row["evidence"]


def test_embedded_verdict_matches_crucible_margin_rule():
    # Faithful to crucible.verdict_for: margin = (tolerance - deviation)/tolerance,
    # MATCH if margin >= 0 else DRIFT; None/negative deviation or non-positive
    # tolerance => UNVERIFIABLE (fail-closed).
    assert verdict_for_measurement(0.0, 0.5) == "MATCH"
    assert verdict_for_measurement(0.5, 0.5) == "MATCH"
    assert verdict_for_measurement(2.0, 0.5) == "DRIFT"
    assert verdict_for_measurement(None, 0.5) == "UNVERIFIABLE"
    assert verdict_for_measurement(0.0, 0.0) == "UNVERIFIABLE"
    assert verdict_for_measurement(-1.0, 0.5) == "UNVERIFIABLE"
