"""Tests for the unified `telos proof <domain>` dispatcher."""

from __future__ import annotations

import json

from proof_surface.cli import main

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

_TRACE = {
    "trace_id": "t1",
    "service": "demo",
    "spans": [
        {
            "span_id": "s2",
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
                "content.sha256": "a" * 64,
                "after.sha256": "c" * 64,
            },
            "events": [],
        }
    ],
}


def test_dispatch_routes_to_agent_action(tmp_path):
    trace = tmp_path / "t.json"
    trace.write_text(json.dumps(_TRACE), encoding="utf-8")
    auth = tmp_path / "a.json"
    auth.write_text(json.dumps(_AUTH), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(
        [
            "agent-action",
            "--trace",
            str(trace),
            "--authorization",
            str(auth),
            "--claim",
            "c",
            "--scope",
            "s",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()


def test_unknown_domain_is_an_error():
    assert main(["nope"]) != 0


def test_help_lists_all_domains(capsys):
    main(["--help"])
    out = capsys.readouterr().out
    assert "agent-action" in out
    assert "visual-measurement" in out
    assert "research-claim" in out
