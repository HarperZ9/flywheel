"""Studio body route status mapping."""

from __future__ import annotations

from typing import Any

ENGINE_UNAVAILABLE_CODES = (
    "studio_engine_unavailable",
    "studio_engine_incomplete",
    "studio_engine_identity_mismatch",
)


def body_step_status(accepted: bool, out: dict[str, Any], errors: list[str]) -> tuple[str, int]:
    if accepted:
        return "accepted", 200
    for code in ENGINE_UNAVAILABLE_CODES:
        if any(code in reason for reason in errors):
            return code, 503
    return str(out.get("decision") or "denied"), 403
