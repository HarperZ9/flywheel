"""Selective Bulletin exposure boundary for lane calls."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


ENV_NAME = "FLYWHEEL_BULLETIN_ACCESS"
POLICY = "flywheel.bulletin-access/v1"
POLICY_SCHEMA = "flywheel.bulletin-access-policy/v1"
_DEFAULT = "full"
_SUPPORTED = ("off", "full")
_RANK = {"off": 0, "full": 1}


def policy_summary() -> dict[str, object]:
    return {
        "schema": POLICY_SCHEMA,
        "env_ceiling": ENV_NAME,
        "supported_modes": list(_SUPPORTED),
        "metadata_mode": "unsupported",
        "default_ceiling": _DEFAULT,
    }


def validate_request_access(value: object) -> None:
    if type(value) is not str or value not in _SUPPORTED:
        raise ValueError


def bulletin_access_denial(
        lane_name: str, tool_name: str, *, requested_access: object = None,
        environ: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    if lane_name != "bulletin":
        return None
    requested, requested_label, requested_error = _requested(requested_access)
    ceiling, ceiling_label, ceiling_error = _ceiling(
        os.environ if environ is None else environ)
    error = requested_error or ceiling_error
    if error:
        return _denial(lane_name, tool_name, requested_label, ceiling_label, error)
    effective = ceiling if _RANK[ceiling] < _RANK[requested] else requested
    if effective != "full":
        return _denial(lane_name, tool_name, requested_label, ceiling_label, None)
    return None


def authorized_bulletin_access_denial(authorized: object) -> dict[str, Any] | None:
    op = dict(getattr(authorized, "operation", {}))
    if (getattr(authorized, "action", None) != "lane.call"
            or op.get("name") != "bulletin"):
        return None
    return bulletin_access_denial(
        "bulletin", str(op.get("tool", "")),
        requested_access=op.get("bulletin_access"))


def _requested(value: object) -> tuple[str, object, str | None]:
    if value is None:
        return _DEFAULT, _DEFAULT, None
    if type(value) is not str:
        return "off", "invalid", "invalid_request"
    normalized = _normalize(value)
    if normalized in _SUPPORTED:
        return normalized, normalized, None
    return "off", "invalid", _mode_error(normalized)


def _ceiling(environ: Mapping[str, str]) -> tuple[str, object, str | None]:
    raw = environ.get(ENV_NAME, "")
    if raw == "":
        return _DEFAULT, _DEFAULT, None
    if type(raw) is not str:
        return "off", "invalid", "invalid_ceiling"
    normalized = _normalize(raw)
    if normalized in _SUPPORTED:
        return normalized, normalized, None
    return "off", "invalid", _mode_error(normalized, env=True)


def _normalize(value: object) -> str:
    return value.strip().lower() if type(value) is str else ""


def _mode_error(value: str, *, env: bool = False) -> str:
    if value == "metadata":
        return "unsupported_access_mode"
    return "invalid_ceiling" if env else "invalid_request"


def _denial(
        lane_name: str, tool_name: str, requested: object, ceiling: object,
        error: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": "flywheel.bulletin-access-denial/v1",
        "error": "bulletin access policy denied the request before transport",
        "governance_denied": True,
        "policy": POLICY,
        "lane": lane_name,
        "tool": tool_name,
        "bulletin_access": "off",
        "bulletin_access_requested": requested,
        "bulletin_access_ceiling": ceiling,
        "network_attempted": False,
        "transport_attempted": False,
        "credential_resolution_attempted": False,
        "does_not_prove": [
            "reviewer blindness",
            "absence of Bulletin content outside this lane dispatch",
            "network origin or IP privacy",
        ],
    }
    if error:
        body["policy_error"] = error
    return body
