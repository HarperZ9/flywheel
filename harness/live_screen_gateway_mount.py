"""Gateway-owned lifecycle mount for the live-screen feed."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .gateway_grant_errors import gateway_error_response
from .gateway_operation import GatewayOperationError, thaw_operation
from .live_screen_gateway_contract import (
    MAX_PREVIEW_BYTES,
    current_frame_evidence,
    validate_live_screen_operation,
    validate_model_delivery,
)
from .live_screen_delivery import DeliveryError
from .live_screen_feed import LiveScreenError, LiveScreenManager
from .live_screen_route import (
    handle_live_screen_get as route_get,
    handle_live_screen_post as route_post,
    handle_live_screen_preview_get as route_preview_get,
)
from .live_screen_scheduler import LiveScreenProducerScheduler
from .live_screen_types import ScreenShareGrant, SourceDescriptor, check_path_id
from .live_screen_gateway_sessions import (
    delivery_error,
    is_empty_json_object,
    live_status,
    revocation_control,
    run_revocation_control,
    session_list,
)


def live_screen_get(handler, path: str, *, now_ns: int | None = None):
    manager, scheduler = _components(handler)
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    if path == "/api/live-screen/status":
        return handler._json(_status(manager), 200)
    if path == "/api/live-screen/sessions":
        body, code = session_list(handler, manager, scheduler, now_ns)
        return handler._json(body, code)
    if path.endswith("/preview"):
        return _preview(handler, path, manager, now_ns=now_ns)
    body, code = route_get(path, manager=manager, owner_ref=handler.owner_ref)
    return handler._json(body, code)


def live_screen_post(handler, path: str, *, now_ns: int | None = None):
    raw = _raw_request(handler)
    if not isinstance(raw, bytes):
        return handler._json(*raw)
    manager, scheduler = _components(handler)
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    if path.endswith("/poll"):
        scheduler.cleanup_expired(owner_ref=handler.owner_ref, now_ns=now_ns)
        body, code = route_post(
            path, raw, manager=manager, grant=None,
            owner_ref=handler.owner_ref, now_ns=now_ns)
        return handler._json(body, code)
    revocation = revocation_control(path)
    if revocation is not None:
        try:
            revoke_without_grant = is_empty_json_object(raw)
        except LiveScreenError as exc:
            return handler._json({"error": {"code": exc.code, "message": str(exc)}},
                                 live_status(exc.code))
        if revoke_without_grant:
            body, code = run_revocation_control(
                path, raw, manager, scheduler, handler.owner_ref, now_ns, revocation)
            return handler._json(body, code)
    if path.endswith("/deliver"):
        try:
            auth, op = _authorize(handler, raw, "live_screen.deliver", resolve=True)
            _matches_delivery_path(path, op)
            from .live_screen_provider_delivery import deliver_bound_sampled_image
            body = deliver_bound_sampled_image(
                manager, authorized=auth, owner_ref=handler.owner_ref,
                now_ns=now_ns, utc_now=_utc_now(manager),
                opener=getattr(handler, "provider_opener", None),
                clock_ns=getattr(manager, "_clock_ns", time.monotonic_ns))
            body = {**body, "authority": _authority(auth)}
            return handler._json(body, 200)
        except DeliveryError as exc:
            body, code = delivery_error(exc)
        except Exception as exc:
            body, code = gateway_error_response(exc)
        return handler._json(body, code)
    try:
        auth, op = _authorize(handler, raw, "live_screen.control")
        _matches_path(path, op)
        body, code = _run_control(path, op, manager, scheduler, handler.owner_ref, now_ns)
        if code == 200:
            body = {**body, "authority": _authority(auth)}
    except Exception as exc:
        body, code = gateway_error_response(exc)
    return handler._json(body, code)


def live_screen_components(handler) -> tuple[LiveScreenManager, LiveScreenProducerScheduler]:
    return _components(handler)


def _components(handler) -> tuple[LiveScreenManager, LiveScreenProducerScheduler]:
    cls, state_root = type(handler), Path(handler.flywheel_home) / "state"
    if getattr(cls, "live_screen_manager", None) is None or getattr(cls, "_live_screen_state_root", None) != state_root:
        cls.live_screen_manager = _new_manager()
        cls.live_screen_scheduler = None
        cls._live_screen_state_root = state_root
    if getattr(cls, "live_screen_scheduler", None) is None:
        cls.live_screen_scheduler = LiveScreenProducerScheduler(
            cls.live_screen_manager,
            clock_ns=getattr(cls.live_screen_manager, "_clock_ns", time.monotonic_ns),
        )
    return cls.live_screen_manager, cls.live_screen_scheduler


def _new_manager() -> LiveScreenManager:
    manager = LiveScreenManager()
    try:
        from .live_screen_sources import coherence_capture_source, coherence_source_descriptors
        for row in coherence_source_descriptors():
            bounds = tuple(row["bounds"]) if row.get("bounds") is not None else None
            desc = SourceDescriptor(row["source_id"], row["kind"], row["label"], bounds,
                                    row["backend"], row["available"], row["unavailable_reason"])
            manager.register_source(desc, lambda row=row: coherence_capture_source(row))
    except Exception:
        pass
    return manager


def _preview(handler, path: str, manager: LiveScreenManager, *, now_ns: int | None):
    meta, raw, code = route_preview_get(path, manager=manager, owner_ref=handler.owner_ref)
    if code != 200:
        return handler._json(meta, code)
    digest = hashlib.sha256(raw).hexdigest()
    media_type = meta.get("media_type")
    expected = (meta.get("frame") or {}).get("frame_sha256")
    if len(raw) > MAX_PREVIEW_BYTES or digest != expected or media_type not in {"image/png", "image/jpeg", "image/webp"}:
        return handler._json({"error": {"code": "FRAME_PREVIEW_INVALID",
                                        "message": "live screen preview is invalid"}}, 409)
    return handler._raw(raw, media_type, 200, {"X-Frame-Sha256": digest, "Cache-Control": "no-store"})


def _run_control(path: str, op: dict, manager, scheduler, owner_ref: str, now_ns: int) -> tuple[dict, int]:
    if op["control"] == "open":
        request = {k: op[k] for k in ("sources", "destination", "model", "delivery_mode",
                                      "buffer_frames_per_source", "max_frame_bytes") if k in op}
        body, code = route_post(path, json.dumps(request).encode(), manager=manager,
                                grant=_screen_grant(op, owner_ref, now_ns),
                                owner_ref=owner_ref, now_ns=now_ns)
        if code == 200:
            scheduler.bind_session(body["session_id"], session_ref=op["body_session_ref"],
                                   instrument_ref=op["instrument_ref"])
            body = {**body, "body_binding": scheduler.bindings[body["session_id"]]}
            if op.get("start_immediately") is True:
                body, code = _start_opened_session(body, manager, scheduler, owner_ref, now_ns)
        return body, code
    body, code = route_post(path, b"{}", manager=manager, grant=None,
                            owner_ref=owner_ref, now_ns=now_ns)
    if code == 200 and op["control"] == "start":
        body = {**body, "producer": {"scheduled": True, "tick_events": len(
            scheduler.start(op["session_id"], owner_ref=owner_ref, now_ns=now_ns))}}
    elif code == 200 and op["control"] == "pause":
        scheduler.pause(op["session_id"], owner_ref=owner_ref)
    elif code == 200 and op["control"] == "resume":
        body = {**body, "producer": {"scheduled": True, "tick_events": len(
            scheduler.start(op["session_id"], owner_ref=owner_ref, now_ns=now_ns))}}
    elif code == 200 and op["control"] == "stop":
        scheduler.stop(op["session_id"], owner_ref=owner_ref)
    return body, code


def _start_opened_session(body: dict, manager, scheduler, owner_ref: str, now_ns: int) -> tuple[dict, int]:
    session_id = body["session_id"]
    started, code = route_post(f"/api/live-screen/sessions/{session_id}/start", b"{}",
                               manager=manager, grant=None,
                               owner_ref=owner_ref, now_ns=now_ns)
    if code != 200:
        _cleanup_started_session(manager, scheduler, session_id, owner_ref, now_ns)
        return started, code
    try:
        events = scheduler.start(session_id, owner_ref=owner_ref, now_ns=now_ns)
    except LiveScreenError as exc:
        _cleanup_started_session(manager, scheduler, session_id, owner_ref, now_ns)
        return _live_error(exc)
    return {**started, "body_binding": body["body_binding"],
            "producer": {"scheduled": True, "tick_events": len(events)}}, 200


def _cleanup_started_session(manager, scheduler, session_id: str, owner_ref: str, now_ns: int) -> None:
    scheduler.stop(session_id, owner_ref=owner_ref)
    try:
        manager.stop_session(session_id, owner_ref=owner_ref, now_ns=now_ns)
    except LiveScreenError:
        pass


def _live_error(exc: LiveScreenError) -> tuple[dict, int]:
    return {"error": {"code": exc.code, "message": str(exc)}}, live_status(exc.code)


def _authorize(handler, raw: bytes, action: str, *, resolve: bool = False):
    from .gateway_grant_route import authorize_gateway_operation
    auth = authorize_gateway_operation(
        action, raw, owner_ref=handler.owner_ref,
        state_root=Path(handler.flywheel_home) / "state",
        clock=handler.clock, workspace_root=Path(handler.root))
    if resolve:
        from .gateway_provider_adapter import resolve_credentials
        auth = resolve_credentials(auth, Path(handler.flywheel_home) / "state")
    return auth, thaw_operation(auth.operation)


def _screen_grant(op: dict, owner_ref: str, now_ns: int) -> ScreenShareGrant:
    source_ids = tuple(item["source_id"] for item in op["sources"])
    return ScreenShareGrant(owner_ref, op["destination"], op["model"], source_ids,
                            now_ns + op["expires_after_ms"] * 1_000_000)


def _matches_path(path: str, op: dict) -> None:
    if op["control"] == "open" and path == "/api/live-screen/sessions":
        return
    parts = path[len("/api/live-screen/sessions/"):].split("/") if path.startswith("/api/live-screen/sessions/") else []
    if len(parts) == 2 and check_path_id(parts[0], "session_id") == op.get("session_id") and parts[1] == op["control"]:
        return
    from .gateway_operation import GatewayOperationError
    raise GatewayOperationError("PERMISSION_DENIED")


def _matches_delivery_path(path: str, op: dict) -> None:
    base = "/api/live-screen/sessions/"
    parts = path[len(base):].split("/") if path.startswith(base) else []
    if (len(parts) == 4 and parts[1] == "sources" and parts[3] == "deliver"
            and check_path_id(parts[0], "session_id") == op["session_id"]
            and check_path_id(parts[2], "source_id") == op["source_id"]):
        return
    raise GatewayOperationError("PERMISSION_DENIED")


def _raw_request(handler) -> bytes | tuple[dict, int]:
    length = handler._content_length()
    if length is None:
        return {"schema": "flywheel.evidence-transport-error/v1",
                "error": {"code": "INVALID_LENGTH",
                          "message": "request length is invalid"}}, 400
    return handler.rfile.read(length)


def _status(manager) -> dict:
    return {"schema": "flywheel.live-screen-gateway-status/v1",
            "manager_ready": True,
            "source_count": len(manager.list_sources()),
            "delivery_modes": {"sampled_image": "supported",
                               "native_video": "unavailable"},
            "routes": {"sources": "/api/live-screen/sources",
                       "open": "POST /api/live-screen/sessions",
                       "control": "POST /api/live-screen/sessions/{session}/start|pause|resume|stop",
                       "events": "POST /api/live-screen/sessions/{session}/poll",
                        "preview": "/api/live-screen/sessions/{session}/sources/{source}/frames/{sequence}/preview"}}


def _utc_now(manager) -> callable:
    return getattr(manager, "_utc_clock", lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def _authority(auth) -> dict:
    return {"action": auth.action, "grant_ref": auth.grant_ref,
            "operation_sha256": auth.operation_sha256,
            "arguments_sha256": auth.arguments_sha256}
