"""Typed, secret-clean provider rejections from bounded Codex events."""
from __future__ import annotations

import json
import math
import re
from typing import Any


_SAFE_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$", re.I)
_MODEL_UNSUPPORTED = re.compile(
    r"(?:the\s+)?['`][^'`\r\n]{1,256}['`]\s+model\s+is\s+not\s+supported\s+when\s+using\s+codex\s+with\s+a\s+chatgpt\s+account\b",
    re.I,
)


class ProviderRejected(RuntimeError):
    def __init__(self, failure_class: str, detail: str):
        super().__init__(detail)
        self.failure_class = failure_class


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    if len(rows) != len({key for key, _ in rows}):
        raise ValueError("duplicate JSON key")
    return dict(rows)


def _bounded(value: Any, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(value, str):
        try:
            return len(value.encode("utf-8")) <= 4096
        except UnicodeEncodeError:
            return False
    if isinstance(value, list):
        return len(value) <= 64 and all(_bounded(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= 64 and all(_bounded(key, depth + 1) and _bounded(item, depth + 1) for key, item in value.items())
    return value is None or isinstance(value, (bool, int)) or (isinstance(value, float) and math.isfinite(value))


def _nested(value: Any) -> tuple[str, dict[str, Any] | None]:
    if not isinstance(value, str) or not value.lstrip().startswith(("{", "[")):
        return "absent", None
    try:
        parsed = json.loads(value, object_pairs_hook=_pairs,
                            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite JSON")))
    except (json.JSONDecodeError, ValueError, RecursionError):
        return "malformed", None
    return ("valid", parsed) if isinstance(parsed, dict) and _bounded(parsed) else ("malformed", None)


def _classify(envelope: dict[str, Any]) -> tuple[str, str] | None:
    status, error = envelope.get("status"), envelope.get("error")
    if type(status) is not int or not 400 <= status <= 599 or not isinstance(error, dict):
        return None
    error_type, message = error.get("type"), error.get("message")
    if not isinstance(error_type, str) or not _SAFE_TYPE.fullmatch(error_type):
        return None
    failure = ("provider_model_unsupported" if error_type == "invalid_request_error"
               and isinstance(message, str) and _MODEL_UNSUPPORTED.search(message) else "provider_rejected")
    safe = {"provider_error_type": error_type, "status": status}
    return failure, json.dumps(safe, sort_keys=True, separators=(",", ":"))


def inspect_provider_events(events: list[dict[str, Any]]) -> tuple[tuple[str, str] | None, bool]:
    """Classify terminal events and reduce their persisted trace to safe fields."""
    rejection, malformed = None, False
    for index, event in enumerate(events):
        if event.get("type") not in {"error", "turn.failed"}:
            continue
        envelopes = [event]
        containers = [event]
        if isinstance(event.get("error"), dict): containers.append(event["error"]); envelopes.append(event["error"])
        for container in containers:
            state, nested = _nested(container.get("message"))
            malformed |= state == "malformed"
            if nested is not None: envelopes.append(nested)
        safe_event = {key: event[key] for key in ("source", "type") if key in event}
        for envelope in envelopes:
            classified = _classify(envelope)
            if classified and rejection is None: rejection = classified
            status, error = envelope.get("status"), envelope.get("error")
            if type(status) is int: safe_event["status"] = status
            if isinstance(error, dict) and isinstance(error.get("type"), str) and _SAFE_TYPE.fullmatch(error["type"]):
                safe_event["error"] = {"type": error["type"]}
        if malformed: safe_event["malformed_provider_message"] = True
        events[index] = safe_event
    return rejection, malformed
