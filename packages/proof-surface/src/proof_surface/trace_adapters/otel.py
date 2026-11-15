"""OpenTelemetry (OTLP/JSON) -> normalized trace adapter.

Flattens an OTLP/JSON export (resourceSpans -> scopeSpans -> spans, with
attributes as key/value lists) into the normalized trace shape that
proof_surface.agent_action.import_trace ingests. A team keeps its existing
OpenTelemetry stack and still emits action receipts.

Note (the honest boundary the dogfood loop also records): an OTel span carries
tool/action/timing, not Telos proof-layer fields. Admission, authority, and
verification are added downstream by the packet builder against an authorization
receipt -- they are never inferred from span data. Stdlib-only.
"""

from __future__ import annotations

from typing import Any

_KIND = {
    0: "unspecified",
    1: "internal",
    2: "server",
    3: "client",
    4: "producer",
    5: "consumer",
}
_STATUS = {0: "unset", 1: "ok", 2: "error"}
_VALID_KINDS = set(_KIND.values())


def _attr_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        raw = value["intValue"]
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "arrayValue" in value:
        return [_attr_value(v) for v in value["arrayValue"].get("values", [])]
    return None


def _flatten_attributes(attrs: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in attrs or []:
        if isinstance(a, dict) and "key" in a:
            out[a["key"]] = _attr_value(a.get("value"))
    return out


def _kind(kind: Any) -> str:
    if isinstance(kind, bool):
        return "unspecified"
    if isinstance(kind, int):
        return _KIND.get(kind, "unspecified")
    if isinstance(kind, str):
        name = kind.upper().replace("SPAN_KIND_", "").lower()
        return name if name in _VALID_KINDS else "unspecified"
    return "unspecified"


def _status(status: Any) -> dict[str, Any]:
    status = status or {}
    code = status.get("code", 0)
    if isinstance(code, str):
        name = code.upper().replace("STATUS_CODE_", "").lower()
    else:
        name = _STATUS.get(code, "unset")
    return {"code": name, "message": status.get("message", "")}


def _ns(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_span(span: dict[str, Any]) -> dict[str, Any]:
    return {
        "span_id": span.get("spanId", ""),
        "parent_span_id": span.get("parentSpanId") or None,
        "name": span.get("name", ""),
        "kind": _kind(span.get("kind", 0)),
        "start_unix_ns": _ns(span.get("startTimeUnixNano")),
        "end_unix_ns": _ns(span.get("endTimeUnixNano")),
        "status": _status(span.get("status")),
        "attributes": _flatten_attributes(span.get("attributes")),
        "events": span.get("events", []) or [],
    }


def _service_name(resource: Any) -> str:
    attrs = _flatten_attributes((resource or {}).get("attributes"))
    value = attrs.get("service.name", "")
    return value if isinstance(value, str) else ""


def normalize_otel(export: dict[str, Any]) -> dict[str, Any]:
    """Normalize an OTLP/JSON export into the proof-surface trace shape."""
    spans: list[dict[str, Any]] = []
    service = ""
    trace_id = ""
    for resource_spans in export.get("resourceSpans", []) or []:
        if not service:
            service = _service_name(resource_spans.get("resource"))
        scope_spans = (
            resource_spans.get("scopeSpans")
            or resource_spans.get("instrumentationLibrarySpans")
            or []
        )
        for scope in scope_spans:
            for span in scope.get("spans", []) or []:
                if not trace_id:
                    trace_id = span.get("traceId", "")
                spans.append(_normalize_span(span))
    return {"trace_id": trace_id, "service": service, "spans": spans}
