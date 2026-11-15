"""Tests for the run-tree (LangSmith/Langfuse-style) trace adapter."""

from __future__ import annotations

from proof_surface.agent_action import import_trace
from proof_surface.trace_adapters import normalize_run_tree

_HEX = "a" * 64
_HEX2 = "c" * 64


def _run_tree():
    return {
        "id": "root",
        "trace_id": "run-abc",
        "name": "agent-run",
        "run_type": "chain",
        "start_time": 1,
        "end_time": 9,
        "child_runs": [
            {
                "id": "s2",
                "parent_run_id": "root",
                "name": "fs.write",
                "run_type": "tool",
                "start_time": 2,
                "end_time": 5,
                "extra": {
                    "metadata": {
                        "actor.id": "user:zain",
                        "action.kind": "fs.write",
                        "action.target": "/work/config.json",
                        "side_effect.class": "write",
                        "content.sha256": _HEX,
                        "after.sha256": _HEX2,
                    }
                },
            }
        ],
    }


def test_normalize_run_tree_flattens_and_carries_action_metadata():
    trace = normalize_run_tree(_run_tree(), service="agent-run")
    assert trace["service"] == "agent-run"
    ids = [s["span_id"] for s in trace["spans"]]
    assert "root" in ids and "s2" in ids
    s2 = next(s for s in trace["spans"] if s["span_id"] == "s2")
    assert s2["parent_span_id"] == "root"
    assert s2["kind"] == "client"  # run_type tool
    assert s2["attributes"]["tool.name"] == "fs.write"  # from run name
    assert s2["attributes"]["action.target"] == "/work/config.json"


def test_run_tree_normalized_feeds_the_agent_action_importer():
    trace = normalize_run_tree(_run_tree(), service="agent-run")
    result = import_trace(trace)
    assert [a.action_id for a in result.actions] == ["s2"]
    action = result.actions[0]
    assert action.action_kind == "fs.write"
    assert action.target == "/work/config.json"
    assert action.after_digest == _HEX2
