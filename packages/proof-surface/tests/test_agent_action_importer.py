"""Tests for the agent-action trace importer.

The importer walks a normalized (OTel-shaped) span tree and turns material
(side-effecting) spans into ActionRecords; read-only/internal spans become
context, never silently dropped.
"""

from __future__ import annotations

from proof_surface.agent_action import import_trace


def _span(span_id, parent, name, attributes, kind="client"):
    return {
        "span_id": span_id,
        "parent_span_id": parent,
        "name": name,
        "kind": kind,
        "start_unix_ns": 0,
        "end_unix_ns": 1,
        "status": {"code": "ok", "message": ""},
        "attributes": attributes,
        "events": [],
    }


def test_side_effecting_span_becomes_an_action_with_mapped_fields():
    trace = {
        "trace_id": "t1",
        "service": "demo-agent",
        "spans": [
            _span(
                "s2",
                None,
                "write config",
                {
                    "actor.id": "user:zain",
                    "agent.id": "agent:claude",
                    "model.id": "claude-opus-4-8",
                    "tool.name": "fs",
                    "action.kind": "fs.write",
                    "action.target": "/work/config.json",
                    "side_effect.class": "write",
                    "cost.tokens": 12,
                    "cost.wall_ms": 4,
                },
            ),
        ],
    }

    result = import_trace(trace)

    assert [a.action_id for a in result.actions] == ["s2"]
    action = result.actions[0]
    assert action.actor == "user:zain"
    assert action.agent == "agent:claude"
    assert action.model == "claude-opus-4-8"
    assert action.tool == "fs"
    assert action.action_kind == "fs.write"
    assert action.target == "/work/config.json"
    assert action.side_effect_class == "write"
    assert action.cost == {"tokens": 12, "wall_ms": 4}
    # deterministic 64-hex content address over the canonical span
    assert len(action.span_digest) == 64
    assert result.flagged == []


def test_action_captures_side_effect_evidence_from_span():
    trace = {
        "trace_id": "t1",
        "service": "demo-agent",
        "spans": [
            _span(
                "s2",
                None,
                "write config",
                {
                    "tool.name": "fs",
                    "action.kind": "fs.write",
                    "action.target": "/work/config.json",
                    "side_effect.class": "write",
                    "content.sha256": "a" * 64,
                    "before.sha256": "b" * 64,
                    "after.sha256": "c" * 64,
                    "reversible": True,
                    "rollback.ref": "backup-1",
                },
            ),
        ],
    }

    action = import_trace(trace).actions[0]

    assert action.content_sha256 == "a" * 64
    assert action.before_digest == "b" * 64
    assert action.after_digest == "c" * 64
    assert action.reversible is True
    assert action.rollback_ref == "backup-1"


def test_read_only_span_is_context_not_action():
    trace = {
        "trace_id": "t1",
        "service": "demo-agent",
        "spans": [
            _span(
                "s1",
                None,
                "read file",
                {
                    "tool.name": "fs",
                    "action.kind": "fs.read",
                    "action.target": "/work/x",
                    "side_effect.class": "read",
                },
                kind="internal",
            ),
        ],
    }

    result = import_trace(trace)

    assert result.actions == []
    assert [c.span_id for c in result.context_spans] == ["s1"]


def test_side_effecting_span_without_target_is_flagged_not_dropped():
    trace = {
        "trace_id": "t1",
        "service": "demo-agent",
        "spans": [
            _span("s1", None, "mystery write", {"side_effect.class": "write"}),
        ],
    }

    result = import_trace(trace)

    assert result.actions == []
    assert [f.span_id for f in result.flagged] == ["s1"]
    assert "target" in result.flagged[0].reason
