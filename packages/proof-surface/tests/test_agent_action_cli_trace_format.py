"""The agent-action CLI can ingest a raw OTel export via --trace-format."""

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

_OTEL = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "demo-agent"}}
                ]
            },
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "traceId": "abc123",
                            "spanId": "s2",
                            "parentSpanId": "",
                            "name": "write config",
                            "kind": 3,
                            "startTimeUnixNano": "1000",
                            "endTimeUnixNano": "5200",
                            "status": {"code": 1},
                            "attributes": [
                                {
                                    "key": "actor.id",
                                    "value": {"stringValue": "user:zain"},
                                },
                                {"key": "tool.name", "value": {"stringValue": "fs"}},
                                {
                                    "key": "action.kind",
                                    "value": {"stringValue": "fs.write"},
                                },
                                {
                                    "key": "action.target",
                                    "value": {"stringValue": "/work/config.json"},
                                },
                                {
                                    "key": "side_effect.class",
                                    "value": {"stringValue": "write"},
                                },
                                {
                                    "key": "content.sha256",
                                    "value": {"stringValue": "a" * 64},
                                },
                                {
                                    "key": "after.sha256",
                                    "value": {"stringValue": "c" * 64},
                                },
                            ],
                            "events": [],
                        }
                    ]
                }
            ],
        }
    ]
}


def test_cli_ingests_a_raw_otel_export(tmp_path):
    trace = tmp_path / "otel.json"
    trace.write_text(json.dumps(_OTEL), encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(_AUTH), encoding="utf-8")
    out = tmp_path / "out"

    rc = main(
        [
            "--trace",
            str(trace),
            "--trace-format",
            "otel",
            "--authorization",
            str(auth),
            "--claim",
            "The agent wrote /work/config.json (from an OpenTelemetry trace).",
            "--scope",
            "One write; network excluded.",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert validate_agent_action_packet(packet) == []
    assert packet["actions"][0]["action_kind"] == "fs.write"
    assert packet["verdicts"]["overall"] == "MATCH"
