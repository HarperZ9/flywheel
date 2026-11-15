"""Tests for the `telos proof agent-action` CLI seam.

One command turns a trace + a grant into an artifact folder: packet.json,
report.md, and the crucible thesis/measurements files for independent
re-derivation.
"""

from __future__ import annotations

import json

from proof_surface.agent_action import validate_agent_action_packet
from proof_surface.agent_action.cli import main

_AUTH = {
    "authorization_version": "0.1",
    "receipt_id": "auth-1",
    "kind": "authorization-grant",
    "principal": {"id": "user:zain"},
    "agent": {"id": "agent:claude"},
    "intent": "write the demo config file",
    "scope": {
        "allowed_actions": ["fs.write"],
        "allowed_targets": ["/work/config.json"],
    },
    "granted_at": "2020-01-01T00:00:00+00:00",
    "expires_at": "2999-01-01T00:00:00+00:00",
    "revoked": False,
}

_TRACE = {
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
                "action.target": "/work/config.json",
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


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_cli_emits_a_valid_packet_and_all_artifacts(tmp_path, capsys):
    trace = _write(tmp_path, "trace.json", _TRACE)
    auth = _write(tmp_path, "auth.json", _AUTH)
    out = tmp_path / "out"

    rc = main(
        [
            "--trace",
            str(trace),
            "--authorization",
            str(auth),
            "--claim",
            "The agent wrote one config file under grant auth-1.",
            "--scope",
            "One filesystem write under /work.",
            "--packet-id",
            "pkt-1",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert validate_agent_action_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"
    assert (out / "report.md").exists()
    assert (out / "crucible-thesis.json").exists()
    assert (out / "crucible-measurements.json").exists()
    # crucible input contract: claim carries a falsifier
    thesis = json.loads((out / "crucible-thesis.json").read_text(encoding="utf-8"))
    assert thesis["claims"][0]["falsification"]


def test_cli_returns_nonzero_when_trace_missing(tmp_path, capsys):
    auth = _write(tmp_path, "auth.json", _AUTH)
    rc = main(
        [
            "--trace",
            str(tmp_path / "nope.json"),
            "--authorization",
            str(auth),
            "--claim",
            "c",
            "--scope",
            "s",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert rc != 0
