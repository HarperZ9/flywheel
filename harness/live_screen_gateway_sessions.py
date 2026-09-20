"""Owner-scoped live-screen session recovery and revocation helpers."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from .live_screen_feed import LiveScreenError
from .live_screen_route import handle_live_screen_post as route_post
from .live_screen_types import check_path_id


def session_list(handler, manager, scheduler, now_ns: int) -> tuple[dict, int]:
    try:
        scheduler.cleanup_expired(owner_ref=handler.owner_ref, now_ns=now_ns)
        query = parse_qs(urlsplit(getattr(handler, "path", "") or "").query,
                         keep_blank_values=False, strict_parsing=False)
        wanted = query.get("body_session_ref", [])
        if len(wanted) > 1:
            raise LiveScreenError("INVALID_ID", "body_session_ref must be a stable identifier")
        body_session_ref = check_path_id(wanted[0], "body_session_ref") if wanted else None
        rows = []
        for session_id, session in sorted(getattr(manager, "_sessions", {}).items()):
            if session.owner_ref != handler.owner_ref:
                continue
            binding = scheduler.bindings.get(session_id)
            if body_session_ref and (not binding or binding.get("session_ref") != body_session_ref):
                continue
            row = manager.session_status(session_id, owner_ref=handler.owner_ref, now_ns=now_ns)
            rows.append({**row, "body_binding": dict(binding)} if binding else row)
        return {"schema": "flywheel.live-screen-session-list/v1",
                "sessions": rows, "count": len(rows)}, 200
    except LiveScreenError as exc:
        return {"error": {"code": exc.code, "message": str(exc)}}, live_status(exc.code)


def revocation_control(path: str) -> tuple[str, str] | None:
    base = "/api/live-screen/sessions/"
    if not path.startswith(base):
        return None
    parts = path[len(base):].split("/")
    if len(parts) != 2 or parts[1] not in {"pause", "stop"}:
        return None
    return check_path_id(parts[0], "session_id"), parts[1]


def run_revocation_control(path: str, raw: bytes, manager, scheduler, owner_ref: str,
                           now_ns: int, revocation: tuple[str, str]) -> tuple[dict, int]:
    session_id, action = revocation
    try:
        if json_object(raw) != {}:
            raise LiveScreenError("INVALID_REQUEST", "revocation controls accept an empty JSON object")
        if action == "stop":
            scheduler.stop(session_id, owner_ref=owner_ref)
        body, code = route_post(path, b"{}", manager=manager, grant=None,
                                owner_ref=owner_ref, now_ns=now_ns)
        if code == 200 and action == "pause":
            scheduler.pause(session_id, owner_ref=owner_ref)
        return body, code
    except LiveScreenError as exc:
        return {"error": {"code": exc.code, "message": str(exc)}}, live_status(exc.code)


def is_empty_json_object(raw: bytes) -> bool:
    return json_object(raw) == {}


def json_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8") if raw else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LiveScreenError("MALFORMED_JSON", "request body is not valid JSON")
    if not isinstance(value, dict):
        raise LiveScreenError("INVALID_REQUEST", "request body must be an object")
    return value


def delivery_error(exc) -> tuple[dict, int]:
    return {"error": {"code": exc.code, "message": str(exc)}}, live_status(exc.code)


def live_status(code: str) -> int:
    if code in {"NOT_FOUND", "SESSION_NOT_FOUND", "FRAME_NOT_FOUND"}:
        return 404
    if code.endswith("NOT_AUTHORIZED") or code in {"SCREEN_SHARE_EXPIRED", "PERMISSION_REQUIRED"}:
        return 403
    if code in {"EXTERNAL_ACTION_FAILED", "PROVIDER_DELIVERY_FAILED"}:
        return 502
    if code == "OPERATION_DEADLINE_EXCEEDED":
        return 504
    return 400
