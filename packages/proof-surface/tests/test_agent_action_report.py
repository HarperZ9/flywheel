"""Tests for the agent-action reviewer report (Markdown).

The report is the human-facing surface. Its load-bearing section is the
Trace-vs-Receipt comparison: it must make explicit what a raw observability
trace shows versus what the receipt adds (admission, side-effect class,
compensation, verdict).
"""

from __future__ import annotations

from proof_surface.agent_action import (
    attach_verdicts,
    build_agent_action_packet,
    render_report,
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


def _trace(target="/work/config.json"):
    return {
        "trace_id": "t1",
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
                },
                "events": [],
            }
        ],
    }


def _allow_packet():
    return attach_verdicts(
        build_agent_action_packet(
            _trace(),
            _auth(["fs.write"], ["/work/config.json"]),
            claim="The agent wrote one config file under grant auth-1.",
            scope="One filesystem write under /work; network excluded.",
            packet_id="pkt-1",
        )
    )


def test_report_shows_claim_verdict_actions_and_side_effects():
    md = render_report(_allow_packet())
    assert "The agent wrote one config file under grant auth-1." in md
    assert "MATCH" in md
    assert "/work/config.json" in md
    assert "fs.write" in md
    assert "write" in md  # side-effect class


def test_report_has_trace_vs_receipt_comparison():
    md = render_report(_allow_packet())
    assert "Trace" in md and "Receipt" in md
    lowered = md.lower()
    assert "admission" in lowered
    assert "side effect" in lowered or "side-effect" in lowered
    assert "verdict" in lowered


def test_report_surfaces_a_denied_action_and_its_reason():
    packet = attach_verdicts(
        build_agent_action_packet(
            _trace(target="/etc/passwd"),
            _auth(["fs.write"], ["/work/config.json"]),
            claim="The agent attempted a write outside its grant.",
            scope="Grant limited to /work/config.json.",
            packet_id="pkt-2",
        )
    )
    md = render_report(packet)
    assert "DRIFT" in md
    assert "deny" in md.lower()
    assert "outside the grant scope" in md


def test_report_is_a_nonempty_string():
    assert isinstance(render_report(_allow_packet()), str)
    assert len(render_report(_allow_packet())) > 200
