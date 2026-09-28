"""Capture evidence normalization for the Studio body contract."""

from __future__ import annotations

import re
from typing import Any

from .live_screen_types import LiveScreenError, check_id

_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = (
    "capture_session_ref",
    "source_ref",
    "latest_frame_ref",
    "latest_delivered_frame_age_ms",
    "latest_frame_captured_at",
    "frame_sha256",
)


class CaptureContractError(ValueError):
    pass


def capture_request(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CaptureContractError("capture_request must be an object")
    out: dict[str, Any] = _empty_request()
    for key in _FIELDS:
        if key in value:
            out[key] = _capture_field(key, value[key])
    return out


def capture_evidence(value: dict[str, Any] | None, session_ref: str, instrument_ref: str) -> dict[str, Any]:
    if value is None:
        return {
            **_empty_request(),
            "available": False,
            "validated": False,
            "status": "capture_manager_unavailable",
            "session_ref": session_ref,
            "instrument_ref": instrument_ref,
        }
    if not isinstance(value, dict) or value.get("validated") is not True:
        raise CaptureContractError("capture_evidence must be validated by the capture manager")
    if value.get("session_ref") != session_ref or value.get("instrument_ref") != instrument_ref:
        raise CaptureContractError("capture_evidence binding does not match snapshot target")
    return {
        **{key: _capture_field(key, value.get(key)) for key in _FIELDS},
        "available": True,
        "validated": True,
        "status": "validated",
        "session_ref": session_ref,
        "instrument_ref": instrument_ref,
    }


def _empty_request() -> dict[str, Any]:
    return {
        "capture_session_ref": None,
        "source_ref": None,
        "latest_frame_ref": None,
        "latest_delivered_frame_age_ms": None,
        "latest_frame_captured_at": None,
        "frame_sha256": None,
        "validated": False,
        "status": "not_checked_without_capture_manager",
    }


def _capture_field(key: str, value: Any) -> Any:
    if key.endswith("_ref"):
        return _optional_ref(value, key)
    if key == "latest_delivered_frame_age_ms":
        return _optional_age(value)
    if key == "frame_sha256":
        return _optional_sha(value)
    if key == "latest_frame_captured_at" and value is not None and not isinstance(value, str):
        raise CaptureContractError("latest_frame_captured_at must be a string")
    return value


def _optional_ref(value: Any, name: str) -> str | None:
    if value is None:
        return None
    try:
        return check_id(value, name)
    except LiveScreenError as exc:
        raise CaptureContractError(f"{name} must be a stable ref without slashes")


def _optional_age(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise CaptureContractError("latest_delivered_frame_age_ms must be a non-negative integer")
    return value


def _optional_sha(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _RAW_SHA256.fullmatch(value) is None:
        raise CaptureContractError("frame_sha256 must be raw sha256")
    return value
