"""Provider fault formatting for existing model-call boundaries.

The durable fact lives in ``model_faults.capture``. This module only turns that
bounded, redacted reading into the short ``BackendError`` text the current
runtime already carries upward. It never retries a call and never treats a
provider's advisory timing header as permission to wait and try again. The
line ends with one sentence in plain words (provider_retry_advice) that says
whether trying again could help and when, because the person reading the line
is the only one who acts on it.
"""
from __future__ import annotations

import json
import urllib.error
from typing import Any

from . import model_dialects, model_faults, model_redaction
from .provider_retry_advice import retry_advice

HTTP_ERROR_BODY_LIMIT = 65536
TRUNCATED_HTTP_ERROR_BODY = "[provider_error_body_truncated]"
LIMIT_FIELD_KEYS = ("type", "code", "status")


def redacted_text(text: Any, *, limit: int = 200) -> str:
    """Text safe to place in an exception or log line."""
    return model_redaction.scrub(text, limit=limit)["text"]


def _headers(value: Any) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    items = getattr(value, "items", None)
    if callable(items):
        return {str(k): v for k, v in items()}
    return {}


def body_from_http_error(error: urllib.error.HTTPError) -> Any:
    raw = error.read(HTTP_ERROR_BODY_LIMIT + 1)
    if len(raw) > HTTP_ERROR_BODY_LIMIT:
        return {"error": TRUNCATED_HTTP_ERROR_BODY, "body_truncated": True}
    if not raw:
        return {}                      # an empty error body is no body, as before
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", "replace")
    else:
        text = str(raw or "")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"error": text}


def _dialect(kind: str, explicit: str) -> str:
    return explicit or model_dialects.dialect_for(kind) or model_dialects.OPENAI


def _append_value(parts: list[str], label: str, value: Any) -> None:
    if value is not None and value != "":
        parts.append(f"{label}={redacted_text(str(value))}")


def _append_deadlines(parts: list[str], rows: Any) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        header = redacted_text(str(row.get("header", "deadline")))
        basis = redacted_text(str(row.get("basis", "unknown_basis")))
        if "seconds" in row:
            parts.append(f"{header} {basis}={row['seconds']}s")
        elif "epoch" in row:
            parts.append(f"{header} {basis}={row['epoch']}")
        elif row.get("read") is False:
            parts.append(f"{header} {basis}=unread")


def limit_fields(body: Any) -> dict:
    """The three error fields a budget reader compares by exact value.

    ``error.type``, ``error.code`` and ``error.status``, kept only when they are
    a string or a whole number, with each string redacted and bounded. This is
    everything limit_signal.provider_body_limit reads, so an error can carry it
    beside a redacted body and no reader needs the provider's raw text."""
    error = body.get("error") if type(body) is dict else None
    if type(error) is not dict:
        return {}
    kept = {}
    for key in LIMIT_FIELD_KEYS:
        value = error.get(key)
        if type(value) is int:
            kept[key] = value
        elif type(value) is str:
            kept[key] = redacted_text(value, limit=128)
    return {"error": kept} if kept else {}


def read_provider_fault(name: str, status: Any, body: Any, *,
                        headers: Any = None, dialect: str = "",
                        kind: str = "") -> tuple:
    """The redacted fault record and its one-line description, as a pair."""
    provider = kind or name
    record = model_faults.capture(
        status=status, headers=_headers(headers), body=body,
        dialect=_dialect(provider, dialect), kind=provider)
    status_text = (record.get("status")
                   if record.get("status") is not None else "unknown")
    parts = [
        f"{redacted_text(str(name))} returned {status_text}: provider fault",
        f"status={status_text}",
        f"category={record.get('category')}",
        f"retriable={record.get('retriable')}",
    ]
    _append_value(parts, "message", record.get("message"))
    _append_value(parts, "body_code", record.get("body_code"))
    _append_value(parts, "body_status", record.get("body_status"))
    _append_value(parts, "upstream_status", record.get("upstream_status"))
    _append_value(parts, "upstream_reason", record.get("upstream_reason"))
    _append_deadlines(parts, record.get("deadlines"))
    caveats = record.get("caveats")
    if isinstance(caveats, list) and caveats:
        parts.append("caveats=" + ",".join(redacted_text(str(c)) for c in caveats))
    return record, "; ".join(parts) + ". " + retry_advice(record)


def format_provider_fault(name: str, status: Any, body: Any, *,
                          headers: Any = None, dialect: str = "",
                          kind: str = "") -> str:
    """Return a redacted one-line description of a provider failure."""
    return read_provider_fault(name, status, body, headers=headers,
                               dialect=dialect, kind=kind)[1]


def format_http_error(name: str, error: urllib.error.HTTPError, *,
                      dialect: str = "", kind: str = "") -> str:
    """Read an ``HTTPError`` body once and format it through the fault reader."""
    return format_provider_fault(
        name, getattr(error, "code", None), body_from_http_error(error),
        headers=getattr(error, "headers", None), dialect=dialect,
        kind=kind or name)


__all__ = ["HTTP_ERROR_BODY_LIMIT", "LIMIT_FIELD_KEYS",
           "TRUNCATED_HTTP_ERROR_BODY", "body_from_http_error",
           "format_http_error", "format_provider_fault", "limit_fields",
           "read_provider_fault", "redacted_text"]
