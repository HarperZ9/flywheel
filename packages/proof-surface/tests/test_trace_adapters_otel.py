"""Tests for the OpenTelemetry (OTLP/JSON) trace adapter.

normalize_otel flattens an OTLP/JSON export into the normalized trace shape that
proof_surface.agent_action.import_trace ingests -- so a team can keep its existing
OpenTelemetry stack and still emit action receipts.
"""

from __future__ import annotations

from proof_surface.agent_action import import_trace
from proof_surface.trace_adapters import normalize_otel

_HEX = "a" * 64
_HEX2 = "c" * 64


def _otel_export():
    return {
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
                                    {
                                        "key": "tool.name",
                                        "value": {"stringValue": "fs"},
                                    },
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
                                        "value": {"stringValue": _HEX},
                                    },
                                    {
                                        "key": "after.sha256",
                                        "value": {"stringValue": _HEX2},
                                    },
                                    {"key": "cost.tokens", "value": {"intValue": "12"}},
                                ],
                                "events": [],
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_normalize_otel_flattens_service_spans_and_attributes():
    trace = normalize_otel(_otel_export())
    assert trace["service"] == "demo-agent"
    assert trace["trace_id"] == "abc123"
    span = trace["spans"][0]
    assert span["span_id"] == "s2"
    assert span["parent_span_id"] is None  # empty OTLP parent -> root
    assert span["kind"] == "client"  # OTel SpanKind 3
    assert span["start_unix_ns"] == 1000
    assert span["attributes"]["tool.name"] == "fs"
    assert span["attributes"]["cost.tokens"] == 12  # intValue coerced to int


def test_otel_normalized_trace_feeds_the_agent_action_importer():
    trace = normalize_otel(_otel_export())
    result = import_trace(trace)
    assert [a.action_id for a in result.actions] == ["s2"]
    action = result.actions[0]
    assert action.action_kind == "fs.write"
    assert action.target == "/work/config.json"
    assert action.after_digest == _HEX2
