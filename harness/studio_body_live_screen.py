"""Live-screen evidence bridge for the Studio body route."""

from __future__ import annotations

from typing import Any

_CAPTURE_FIELDS = (
    "capture_session_ref",
    "source_ref",
    "latest_frame_ref",
    "latest_delivered_frame_age_ms",
    "latest_frame_captured_at",
    "frame_sha256",
)


def capture_request_from_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    return {key: body[key] for key in _CAPTURE_FIELDS if key in body}


def capture_snapshot_evidence(session_ref: str, instrument_ref: str, body: Any, *,
                              capture_manager=None, capture_scheduler=None,
                              owner_ref: str | None = None,
                              now_ns: int | None = None) -> dict[str, Any] | None:
    if capture_manager is None or capture_scheduler is None or owner_ref is None:
        return None
    from harness.live_screen_gateway_contract import current_frame_evidence
    return current_frame_evidence(
        manager=capture_manager, scheduler=capture_scheduler,
        owner_ref=owner_ref, session_ref=session_ref,
        instrument_ref=instrument_ref, requested=capture_request_from_body(body),
        now_ns=now_ns)


def capture_claim_problem(step, *, capture_manager=None, capture_scheduler=None,
                          owner_ref: str | None = None,
                          now_ns: int | None = None) -> str:
    content = step.accountable_content()
    if not mentions_capture(content):
        return ""
    if capture_manager is None or capture_scheduler is None or owner_ref is None:
        return "capture_manager_unavailable"
    from harness.live_screen_gateway_contract import validate_model_delivery
    result = validate_model_delivery(
        manager=capture_manager, scheduler=capture_scheduler,
        owner_ref=owner_ref, content=content, now_ns=now_ns)
    if isinstance(result, dict) and result.get("validated") is True:
        return ""
    return str(result.get("status") if isinstance(result, dict) else "capture_evidence_unverified")


def mentions_capture(content: dict[str, Any]) -> bool:
    if any(content.get(key) is not None for key in (
        "capture_session_ref", "latest_frame_ref", "latest_delivered_frame_age_ms",
    )):
        return True
    for part in content.get("model_delivery", {}).get("parts", []):
        if isinstance(part, dict) and (
                "frame_ref" in part or part.get("kind") in {"image", "video", "screen_frame"}):
            return True
    return False
