from __future__ import annotations

from collections import deque
import time
import uuid
from typing import Callable

from .live_screen_cleanup import close_session_resources
from .live_screen_types import (
    DELIVERY_MODES,
    FrameRecord,
    LiveScreenSession,
    LiveScreenError,
    RegisteredSource,
    ScreenShareGrant,
    SourceDescriptor,
    SyntheticCaptureSource,
    check_bounds,
    check_id,
    check_kind,
    check_model_ref,
    fail,
    frame_sha,
    media_type_for,
)


class LiveScreenManager:
    def __init__(self, *, clock_ns: Callable[[], int] = time.monotonic_ns,
                 utc_clock: Callable[[], str] | None = None, max_total_buffer_bytes: int = 64 << 20):
        self._clock_ns = clock_ns
        self._utc_clock = utc_clock or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._max_total_buffer_bytes = max_total_buffer_bytes
        self._reserved_buffer_bytes = 0
        self._sources: dict[str, RegisteredSource] = {}
        self._sessions: dict[str, LiveScreenSession] = {}

    def register_source(self, descriptor: SourceDescriptor, factory: Callable[[], object]) -> None:
        source_id = check_id(descriptor.source_id, "source_id")
        check_kind(descriptor.kind)
        self._sources[source_id] = RegisteredSource(
            SourceDescriptor(source_id, descriptor.kind, str(descriptor.label),
                             check_bounds(descriptor.bounds), str(descriptor.backend),
                             bool(descriptor.available), descriptor.unavailable_reason),
            factory)

    def list_sources(self) -> list[dict]:
        """Gateway must owner/process-scope this inventory before exposing it."""
        return [source.descriptor.to_dict() for source in self._sources.values()]

    def open_session(self, request: dict, *, grant: ScreenShareGrant, owner_ref: str,
                     now_ns: int | None = None) -> dict:
        now_ns = self._now(now_ns)
        self._sweep_expired(now_ns)
        if not isinstance(request, dict):
            fail("INVALID_REQUEST", "session request must be an object")
        source_ids = self._request_sources(request)
        destination = check_id(request.get("destination"), "destination")
        model = check_model_ref(request.get("model"))
        delivery_mode = request.get("delivery_mode")
        if delivery_mode not in DELIVERY_MODES:
            fail("DELIVERY_MODE_UNSUPPORTED", "delivery mode must be sampled_image or native_video")
        buffer_size = self._bounded_int(request.get("buffer_frames_per_source", 2), 1, 12, "buffer_frames_per_source")
        max_frame_bytes = self._bounded_int(request.get("max_frame_bytes", 1 << 20), 1, 4 << 20, "max_frame_bytes")
        reserve = len(source_ids) * buffer_size * max_frame_bytes
        if self._reserved_buffer_bytes + reserve > self._max_total_buffer_bytes:
            fail("BUFFER_BUDGET_EXCEEDED", "requested live screen buffer is too large")
        self._check_grant(grant, owner_ref, source_ids, destination, model, now_ns)
        for sid in source_ids:
            reg = self._sources.get(sid)
            if reg is None:
                fail("UNKNOWN_SOURCE", f"source is not registered: {sid}")
            if not reg.descriptor.available:
                fail("SOURCE_UNAVAILABLE", reg.descriptor.unavailable_reason or "source unavailable")
        session = LiveScreenSession(str(uuid.uuid4()), owner_ref, destination, model, tuple(source_ids),
                                    delivery_mode, grant.expires_at_ns, buffer_size, max_frame_bytes)
        session.buffers = {sid: deque(maxlen=buffer_size) for sid in source_ids}
        session.events = deque(maxlen=max(1, len(source_ids) * buffer_size * 2))
        session.source_sequences = {sid: 0 for sid in source_ids}
        session.dropped_frames = {sid: 0 for sid in source_ids}
        session.reserved_buffer_bytes = reserve
        self._sessions[session.session_id] = session
        self._reserved_buffer_bytes += reserve
        return self.session_status(session.session_id, owner_ref=owner_ref, now_ns=now_ns)

    def start_session(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> dict:
        session = self._session(session_id, owner_ref)
        self._not_expired(session, self._now(now_ns))
        if session.state == "stopped":
            fail("SESSION_STOPPED", "stopped live screen sessions cannot restart")
        if session.state == "created":
            from .live_screen_startup import start_session_sources
            start_session_sources(self, session)
        session.state = "active"
        return self.session_status(session_id, owner_ref=owner_ref, now_ns=now_ns)

    def pause_session(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> dict:
        session = self._session(session_id, owner_ref)
        self._not_expired(session, self._now(now_ns))
        if session.state == "active":
            session.state = "paused"
        return self.session_status(session_id, owner_ref=owner_ref, now_ns=now_ns)

    def resume_session(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> dict:
        session = self._session(session_id, owner_ref)
        self._not_expired(session, self._now(now_ns))
        if session.state == "paused":
            session.state = "active"
        return self.session_status(session_id, owner_ref=owner_ref, now_ns=now_ns)

    def stop_session(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> dict:
        session = self._session(session_id, owner_ref)
        self._release_session(session)
        return self.session_status(session_id, owner_ref=owner_ref)

    def producer_tick(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> list[dict]:
        session = self._session(session_id, owner_ref)
        now_ns = self._now(now_ns)
        self._not_expired(session, now_ns)
        if session.state == "paused":
            return []
        if session.state != "active":
            fail("SESSION_NOT_ACTIVE", "live screen session is not active")
        events = []
        for sid in session.source_ids:
            iterator = session.iterators.get(sid)
            if iterator is None:
                continue
            try:
                raw = next(iterator)
            except StopIteration:
                continue
            event = self._record(session, sid, raw, now_ns).to_event()
            session.events.append(event)
            events.append(event)
        return events

    def read_events(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> list[dict]:
        session = self._session(session_id, owner_ref)
        self._not_expired(session, self._now(now_ns))
        events = list(session.events)
        session.events.clear()
        return events

    def latest_frame(self, session_id: str, source_id: str, *, owner_ref: str,
                     now_ns: int | None = None) -> FrameRecord | None:
        session = self._session(session_id, owner_ref)
        if session.state == "stopped":
            return None
        self._not_expired(session, self._now(now_ns))
        buf = session.buffers.get(source_id)
        return buf[-1] if buf else None

    def preview_frame(self, session_id: str, source_id: str, source_sequence: int,
                      *, owner_ref: str, now_ns: int | None = None) -> FrameRecord:
        session = self._session(session_id, owner_ref)
        self._not_expired(session, self._now(now_ns))
        if type(source_sequence) is not int or source_sequence <= 0:
            fail("INVALID_FRAME_REFERENCE", "source_sequence must be a positive integer")
        buf = session.buffers.get(source_id)
        if not buf:
            fail("FRAME_NOT_FOUND", "frame is not available in the bounded preview buffer")
        for frame in buf:
            if frame.source_sequence == source_sequence:
                return frame
        fail("FRAME_NOT_FOUND", "frame is not available in the bounded preview buffer")

    def frame_for_delivery(self, session_id: str, source_id: str, *, owner_ref: str,
                           grant: ScreenShareGrant, destination: str, model: str,
                           now_ns: int | None = None) -> FrameRecord:
        session = self._session(session_id, owner_ref)
        now_ns = self._now(now_ns)
        if session.state == "stopped":
            fail("SESSION_STOPPED", "stopped session has no deliverable live frame")
        if session.state == "paused":
            fail("SESSION_PAUSED", "paused session has no new deliverable frame")
        if session.state != "active":
            fail("SESSION_NOT_ACTIVE", "live screen session is not active")
        self._not_expired(session, now_ns)
        if source_id not in session.source_ids:
            fail("SOURCE_NOT_IN_SESSION", "source is not selected in this session")
        if destination != session.destination:
            fail("SESSION_DESTINATION_MISMATCH", "destination differs from original session binding")
        if model != session.model:
            fail("SESSION_MODEL_MISMATCH", "model differs from original session binding")
        self._check_grant(grant, owner_ref, (source_id,), destination, model, now_ns)
        frame = self.latest_frame(session_id, source_id, owner_ref=owner_ref, now_ns=now_ns)
        if frame is None:
            fail("NO_FRAME_AVAILABLE", "no live frame has been captured for this source")
        return frame

    def session_status(self, session_id: str, *, owner_ref: str,
                       now_ns: int | None = None) -> dict:
        session = self._session(session_id, owner_ref)
        if session.state != "stopped":
            self._not_expired(session, self._now(now_ns))
        return {"schema": "flywheel.live-screen-session/v1", "session_id": session.session_id,
                "state": session.state, "source_ids": list(session.source_ids),
                "destination": session.destination, "model": session.model, "delivery_mode": session.delivery_mode,
                "frames": {sid: seq for sid, seq in session.source_sequences.items() if seq},
                "dropped_frames": dict(session.dropped_frames),
                **({"cleanup_errors": list(session.cleanup_errors)}
                   if session.cleanup_errors else {})}

    def _record(self, session: LiveScreenSession, sid: str, raw, now_ns: int) -> FrameRecord:
        payload = raw.read()
        if type(payload) is not bytes:
            fail("INVALID_FRAME", "capture frame did not return bytes")
        if len(payload) > session.max_frame_bytes:
            fail("FRAME_TOO_LARGE", "capture frame exceeds session byte budget")
        desc = raw.descriptor
        session.source_sequences[sid] += 1
        session.aggregate_sequence += 1
        width = int(getattr(desc, "width", 0) or 0)
        height = int(getattr(desc, "height", 0) or 0)
        if width <= 0 or height <= 0:
            fail("INVALID_FRAME_GEOMETRY", "frame requires positive width and height")
        buf = session.buffers[sid]
        dropped_before = session.dropped_frames[sid]
        if len(buf) == buf.maxlen:
            session.dropped_frames[sid] += 1
        frame = FrameRecord(session.session_id, sid, session.source_sequences[sid], session.aggregate_sequence,
                            frame_sha(payload), getattr(desc, "timestamp", None) or self._utc_clock(), now_ns,
                            self._utc_clock(), width, height, str(getattr(desc, "pixel_format", "") or "unknown"),
                            media_type_for(getattr(desc, "pixel_format", ""), getattr(raw, "media_type", None)), payload,
                            session.dropped_frames[sid] - dropped_before)
        buf.append(frame)
        return frame

    def _request_sources(self, request: dict) -> list[str]:
        raw = request.get("sources")
        if not isinstance(raw, list) or not raw:
            fail("NO_SOURCES_SELECTED", "choose at least one live screen source")
        ids = []
        for item in raw:
            if not isinstance(item, dict):
                fail("INVALID_SOURCE_SELECTION", "source selections must be objects")
            sid = check_id(item.get("source_id"), "source_id")
            if sid in ids:
                fail("DUPLICATE_SOURCE", f"source selected twice: {sid}")
            ids.append(sid)
        return ids

    def _check_grant(self, grant: ScreenShareGrant, owner_ref: str, source_ids,
                     destination: str, model: str, now_ns: int) -> None:
        if owner_ref != grant.owner_ref:
            fail("OWNER_NOT_AUTHORIZED", "owner does not hold this screen share grant")
        self._not_expired(grant, now_ns)
        if destination != grant.destination:
            fail("DESTINATION_NOT_AUTHORIZED", "destination is outside the screen share grant")
        if model != grant.model:
            fail("MODEL_NOT_AUTHORIZED", "model is outside the screen share grant")
        allowed = set(grant.source_ids)
        for sid in source_ids:
            if sid not in allowed:
                fail("SOURCE_NOT_AUTHORIZED", "source is outside the screen share grant")

    def _not_expired(self, value, now_ns: int) -> None:
        if now_ns >= value.expires_at_ns:
            if isinstance(value, LiveScreenSession):
                self._release_session(value)
                detail = ("; cleanup failed: " + "; ".join(value.cleanup_errors) if value.cleanup_errors else "")
            else:
                detail = ""
            fail("SCREEN_SHARE_EXPIRED", "screen share grant expired" + detail)

    def _session(self, session_id: str, owner_ref: str) -> LiveScreenSession:
        session = self._sessions.get(check_id(session_id, "session_id"))
        if session is None:
            fail("SESSION_NOT_FOUND", "live screen session not found")
        if session.owner_ref != owner_ref:
            fail("OWNER_NOT_AUTHORIZED", "owner does not own this live screen session")
        return session

    def _now(self, now_ns: int | None) -> int:
        return self._clock_ns() if now_ns is None else now_ns

    def _bounded_int(self, value, low: int, high: int, label: str) -> int:
        if type(value) is not int or not low <= value <= high:
            fail("INVALID_REQUEST", f"{label} must be {low}..{high}")
        return value

    def _release_session(self, session: LiveScreenSession) -> None:
        session.cleanup_errors.extend(close_session_resources(session))
        if session.reserved_buffer_bytes:
            self._reserved_buffer_bytes -= session.reserved_buffer_bytes
            session.reserved_buffer_bytes = 0
        session.state = "stopped"
        session.buffers = {sid: deque(maxlen=session.buffer_frames_per_source) for sid in session.source_ids}
        session.events.clear()

    def _sweep_expired(self, now_ns: int) -> None:
        for session in self._sessions.values():
            if session.state != "stopped" and now_ns >= session.expires_at_ns:
                self._release_session(session)
