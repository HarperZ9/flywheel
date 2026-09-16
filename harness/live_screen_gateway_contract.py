"""Gateway-facing live-screen validation and frame evidence helpers."""

from __future__ import annotations

import time

from .live_screen_feed import LiveScreenError
from .live_screen_types import check_id, check_model_ref

MAX_PREVIEW_BYTES = 4 << 20
_CONTROL_ACTIONS = {"start", "pause", "resume", "stop"}


def validate_live_screen_operation(value: dict) -> None:
    if value.get("credential_refs") != []:
        raise ValueError
    control = value.get("control")
    if control == "open":
        _open_shape(value)
        return
    if control in _CONTROL_ACTIONS:
        if set(value) != {"control", "session_id", "data_refs", "credential_refs"}:
            raise ValueError
        check_id(value["session_id"], "session_id")
        return
    raise ValueError


def validate_live_screen_delivery_operation(value: dict) -> None:
    required = {"session_id", "source_id", "destination", "model",
                "delivery_mode", "prompt", "max_output_tokens", "timeout_s",
                "data_refs", "credential_refs"}
    optional = {"max_age_ms"}
    if set(value) - required - optional or required - set(value):
        raise ValueError
    check_id(value["session_id"], "session_id")
    check_id(value["source_id"], "source_id")
    check_id(value["destination"], "destination")
    check_model_ref(value["model"])
    if value["destination"] != "openai_responses:vision":
        raise ValueError
    if value["delivery_mode"] != "sampled_image":
        raise ValueError
    if value.get("data_refs") != []:
        raise ValueError
    if (not isinstance(value.get("credential_refs"), list)
            or len(value["credential_refs"]) != 1):
        raise ValueError
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10_000:
        raise ValueError
    for key, low, high in (("max_output_tokens", 1, 4096),
                           ("timeout_s", 1, 120),
                           ("max_age_ms", 0, 120_000)):
        if key in value and (type(value[key]) is not int or not low <= value[key] <= high):
            raise ValueError


def current_frame_evidence(*, manager, scheduler, owner_ref: str,
                           session_ref: str, instrument_ref: str,
                           requested: dict, now_ns: int | None = None) -> dict | None:
    session_id, source_id = requested.get("capture_session_ref"), requested.get("source_ref")
    if not (session_id and source_id):
        return None
    binding = scheduler.bindings.get(session_id)
    if binding != {"session_ref": session_ref, "instrument_ref": instrument_ref}:
        return None
    try:
        frame = manager.latest_frame(session_id, source_id, owner_ref=owner_ref, now_ns=now_ns)
    except LiveScreenError:
        return None
    if frame is None:
        return None
    return {**binding, "validated": True, "capture_session_ref": session_id,
            "source_ref": source_id, "latest_frame_ref": f"{source_id}:{frame.source_sequence}",
            "latest_delivered_frame_age_ms": frame.age_ms(now_ns or time.monotonic_ns()),
            "latest_frame_captured_at": frame.captured_at_utc,
            "frame_sha256": frame.frame_sha256, "frame": frame.identity()}


def validate_model_delivery(*, manager, scheduler, owner_ref: str, content: dict,
                            now_ns: int | None = None) -> dict:
    parts = content.get("model_delivery", {}).get("parts", [])
    if content.get("latest_frame_ref") is not None and not any(
            isinstance(part, dict) and isinstance(part.get("frame"), dict)
            for part in parts):
        return {"validated": False, "status": "frame_identity_missing"}
    for part in parts:
        if not isinstance(part, dict):
            continue
        if _part_mentions_frame(part) and not isinstance(part.get("frame"), dict):
            return {"validated": False, "status": "frame_identity_missing"}
        frame = part.get("frame")
        from .live_screen_delivery_records import requires_delivery_record, validate_delivery_part
        if requires_delivery_record(part):
            status = validate_delivery_part(manager, owner_ref=owner_ref, part=part)
            if status != "validated":
                return {"validated": False, "status": status}
        if frame and not _frame_exists(manager, scheduler, owner_ref, content, frame, now_ns):
            return {"validated": False, "status": "frame_reference_unverified"}
    return {"validated": True, "status": "validated"}


def _frame_exists(manager, scheduler, owner_ref: str, content: dict, frame: dict, now_ns) -> bool:
    binding = scheduler.bindings.get(frame.get("session_id"))
    if binding != {"session_ref": content.get("session_ref"),
                   "instrument_ref": content.get("instrument_ref")}:
        return False
    try:
        found = manager.preview_frame(frame["session_id"], frame["source_id"],
                                      frame["source_sequence"], owner_ref=owner_ref,
                                      now_ns=now_ns)
    except (KeyError, LiveScreenError):
        return False
    return found.frame_sha256 == frame.get("frame_sha256")


def _part_mentions_frame(part: dict) -> bool:
    return "frame_ref" in part or "frame" in part or part.get("kind") in {"image", "video", "screen_frame"}


def _open_shape(value: dict) -> None:
    required = {"control", "body_session_ref", "instrument_ref", "sources",
                "destination", "model", "delivery_mode", "expires_after_ms",
                "data_refs", "credential_refs"}
    optional = {"buffer_frames_per_source", "max_frame_bytes", "start_immediately"}
    if set(value) - required - optional or required - set(value):
        raise ValueError
    check_id(value["body_session_ref"], "body_session_ref")
    check_id(value["instrument_ref"], "instrument_ref")
    if value["delivery_mode"] != "sampled_image" or not isinstance(value["sources"], list):
        raise ValueError
    for item in value["sources"]:
        if not isinstance(item, dict) or set(item) != {"source_id"}:
            raise ValueError
        check_id(item["source_id"], "source_id")
    for key, low, high in (("expires_after_ms", 1000, 120_000),
                           ("buffer_frames_per_source", 1, 12),
                           ("max_frame_bytes", 1, MAX_PREVIEW_BYTES)):
        if key in value and (type(value[key]) is not int or not low <= value[key] <= high):
            raise ValueError
    if "start_immediately" in value and type(value["start_immediately"]) is not bool:
        raise ValueError
