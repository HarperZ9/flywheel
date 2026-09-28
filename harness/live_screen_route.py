"""Standalone live-screen route hooks for the gateway owner."""

from __future__ import annotations

import json

from .live_screen_feed import LiveScreenError
from .live_screen_types import check_path_id


PREFIX = "/api/live-screen"


def handle_live_screen_get(path: str, *, manager, owner_ref: str) -> tuple[dict, int]:
    try:
        if path == PREFIX + "/sources":
            return {"sources": manager.list_sources()}, 200
        if path.startswith(PREFIX + "/sessions/"):
            session_id = check_path_id(path[len(PREFIX + "/sessions/"):], "session_id")
            return manager.session_status(session_id, owner_ref=owner_ref), 200
        return _error("NOT_FOUND", "live screen route not found", 404)
    except LiveScreenError as exc:
        return _error(exc.code, str(exc), _status(exc.code))


def handle_live_screen_post(path: str, raw: bytes, *, manager, grant, owner_ref: str,
                            now_ns: int) -> tuple[dict, int]:
    try:
        body = _json(raw)
        if path == PREFIX + "/sessions":
            return manager.open_session(body, grant=grant, owner_ref=owner_ref,
                                        now_ns=now_ns), 200
        session_id, action = _session_action(path)
        if action == "start":
            return manager.start_session(session_id, owner_ref=owner_ref, now_ns=now_ns), 200
        if action == "pause":
            return manager.pause_session(session_id, owner_ref=owner_ref, now_ns=now_ns), 200
        if action == "resume":
            return manager.resume_session(session_id, owner_ref=owner_ref, now_ns=now_ns), 200
        if action == "stop":
            return manager.stop_session(session_id, owner_ref=owner_ref, now_ns=now_ns), 200
        if action == "poll":
            return {"events": manager.read_events(session_id, owner_ref=owner_ref,
                                                  now_ns=now_ns)}, 200
        return _error("NOT_FOUND", "live screen route not found", 404)
    except LiveScreenError as exc:
        return _error(exc.code, str(exc), _status(exc.code))


def handle_live_screen_preview_get(path: str, *, manager, owner_ref: str) -> tuple[dict, bytes, int]:
    try:
        frame = manager.preview_frame(*_preview_ref(path), owner_ref=owner_ref)
        return {
            "frame": frame.identity(),
            "media_type": frame.media_type,
            "width": frame.width,
            "height": frame.height,
        }, frame.payload, 200
    except LiveScreenError as exc:
        return _error(exc.code, str(exc), _status(exc.code))[0], b"", _status(exc.code)


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8") if raw else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LiveScreenError("MALFORMED_JSON", "request body is not valid JSON")
    if not isinstance(value, dict):
        raise LiveScreenError("INVALID_REQUEST", "request body must be an object")
    return value


def _session_action(path: str) -> tuple[str, str]:
    base = PREFIX + "/sessions/"
    if not path.startswith(base):
        raise LiveScreenError("NOT_FOUND", "live screen route not found")
    tail = path[len(base):].split("/")
    if len(tail) != 2:
        raise LiveScreenError("NOT_FOUND", "live screen route not found")
    return check_path_id(tail[0], "session_id"), tail[1]


def _preview_ref(path: str) -> tuple[str, str, int]:
    base = PREFIX + "/sessions/"
    if not path.startswith(base):
        raise LiveScreenError("NOT_FOUND", "live screen preview route not found")
    parts = path[len(base):].split("/")
    if len(parts) != 6 or parts[1] != "sources" or parts[3] != "frames" or parts[5] != "preview":
        raise LiveScreenError("NOT_FOUND", "live screen preview route not found")
    try:
        seq = int(parts[4])
    except ValueError:
        raise LiveScreenError("INVALID_FRAME_REFERENCE", "source_sequence must be an integer")
    return check_path_id(parts[0], "session_id"), check_path_id(parts[2], "source_id"), seq


def _error(code: str, message: str, status: int) -> tuple[dict, int]:
    return {"error": {"code": code, "message": message}}, status


def _status(code: str) -> int:
    if code in {"NOT_FOUND", "SESSION_NOT_FOUND"}:
        return 404
    if code.endswith("NOT_AUTHORIZED") or code == "SCREEN_SHARE_EXPIRED":
        return 403
    return 400
