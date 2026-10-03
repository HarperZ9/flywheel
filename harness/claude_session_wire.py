"""Strict JSON and frame validation for Claude stream-json transport."""
from __future__ import annotations

import json
import math
from types import MappingProxyType
from typing import Any


class ClaudeSessionWireError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def decode_json_frame(raw: bytes | str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        data = _reject_nonfinite_json(
            json.loads(text, parse_constant=_reject_constant))
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise ClaudeSessionWireError(
            "malformed_json", "frame is not strict finite JSON") from exc
    if not isinstance(data, dict):
        raise ClaudeSessionWireError(
            "malformed_event", "frame JSON must be an object")
    return data


def encode_json_frame(frame: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(frame, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ClaudeSessionWireError(
            "invalid_json_frame", "frame cannot be encoded as strict JSON") from exc
    return text.encode("utf-8") + b"\n"


def freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(k): freeze_json(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze_json(v) for v in value)
    return value


def validate_result_frame(raw: dict[str, Any]) -> bool:
    return (
        isinstance(raw.get("subtype"), str)
        and _is_number(raw.get("duration_ms"))
        and _is_number(raw.get("duration_api_ms"))
        and isinstance(raw.get("is_error"), bool)
        and type(raw.get("num_turns")) is int
        and isinstance(raw.get("session_id"), str)
    )


def _is_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _reject_nonfinite_json(value: Any) -> Any:
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite JSON number is not allowed")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_json(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_json(item)
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value} is not allowed")
