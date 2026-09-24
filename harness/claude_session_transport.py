"""Stdlib Claude Code streaming JSON transport."""
from __future__ import annotations
import queue
import threading
from typing import Any
from .claude_session_contract import ClaudeControlRequest, ClaudePermissionDecision, ClaudeSessionEvent, ClaudeSessionLaunchConfig, ClaudeSessionProtocolEvent, build_claude_session_argv, build_user_message, session_id_from_event
from .claude_session_control import ControlResponseTable, ClaudeSessionTransportError, close_pipe, require_positive
from .claude_session_wire import ClaudeSessionWireError, decode_json_frame, encode_json_frame, freeze_json, validate_result_frame
_KNOWN_EVENT_TYPES = frozenset({"assistant", "result", "system", "user"})
_INCOMING_CONTROL_SUBTYPES = frozenset({"can_use_tool", "hook_callback", "mcp_message"})
class ClaudeSessionTransport:
    def __init__(self, *, incoming, outgoing, default_timeout: float = 1.0,
                 event_queue_size: int = 256, protocol_queue_size: int = 256,
                 control_queue_size: int = 64, max_line_bytes: int = 1024 * 1024):
        require_positive("event_queue_size", event_queue_size)
        require_positive("protocol_queue_size", protocol_queue_size)
        require_positive("control_queue_size", control_queue_size)
        require_positive("max_line_bytes", max_line_bytes)
        self._incoming = incoming
        self._outgoing = outgoing
        self._default_timeout = default_timeout
        self._max_line_bytes = max_line_bytes
        self._events = queue.Queue(maxsize=event_queue_size)
        self._protocol = queue.Queue(maxsize=protocol_queue_size)
        self._control_requests = queue.Queue(maxsize=control_queue_size)
        self._sdk_responses = ControlResponseTable()
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._sequence = 0
        self._protocol_sequence = 0
        self._awaiting_result = False
        self._event_overflowed = False
        self._protocol_overflowed = False
        self._recovery_needed = False
        self._session_id = ""
        self._control_token_counter = 0
        self._pending_control_tokens: dict[str, str] = {}
        self._resolved_control_ids: set[str] = set()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
    @property
    def session_id(self) -> str:
        with self._state_lock:
            return self._session_id
    def initialize(self, *, timeout: float | None = None) -> dict[str, Any]:
        return self._send_sdk_request(
            "init", {"subtype": "initialize", "hooks": None}, timeout=timeout)
    def interrupt(self, *, timeout: float | None = None) -> dict[str, Any]:
        return self._send_sdk_request("interrupt", {"subtype": "interrupt"}, timeout=timeout)
    def send_user_message(self, content: str | list[dict[str, Any]], *,
                          parent_tool_use_id: str | None = None) -> None:
        raw = self._encode_frame(build_user_message(content, parent_tool_use_id=parent_tool_use_id))
        with self._write_lock:
            with self._state_lock:
                self._ensure_writable_locked()
                if self._pending_control_tokens:
                    self._recovery_needed = True; raise ClaudeSessionTransportError("pending_control_request", "provider control request is unresolved")
                if self._awaiting_result:
                    raise ClaudeSessionTransportError("turn_in_flight", "previous user message has no result yet")
                self._awaiting_result = True
            self._write_raw_locked(raw, sensitive=False)
    def pop_event(self, timeout: float | None = None): return self._pop(self._events, timeout)
    def pop_protocol_event(self, timeout: float | None = None): return self._pop(self._protocol, timeout)
    def pop_control_request(self, timeout: float | None = None): return self._pop(self._control_requests, timeout)
    def send_permission_decision(self, request: ClaudeControlRequest,
                                 decision: ClaudePermissionDecision) -> None:
        if request.subtype != "can_use_tool":
            raise ClaudeSessionTransportError(
                "not_permission_request", "control request is not a permission request")
        self.send_control_response(request, decision.to_typescript_callback_result())
    def send_control_response(self, request: ClaudeControlRequest,
                              response: dict[str, Any]) -> None:
        self._check_pending_request(request)
        raw = self._encode_frame({"type": "control_response", "response": {
            "subtype": "success", "request_id": request.request_id, "response": response}})
        with self._write_lock:
            with self._state_lock:
                self._ensure_writable_locked()
                self._check_pending_request_locked(request)
            self._write_raw_locked(raw, sensitive=True)
            with self._state_lock:
                self._check_pending_request_locked(request)
                del self._pending_control_tokens[request.request_id]
                self._resolved_control_ids.add(request.request_id)
    def event_overflowed(self) -> bool:
        with self._state_lock: return self._event_overflowed
    def protocol_overflowed(self) -> bool:
        with self._state_lock: return self._protocol_overflowed
    def needs_recovery(self) -> bool:
        with self._state_lock: return self._recovery_needed
    def has_pending_control_requests(self) -> bool:
        with self._state_lock: return bool(self._pending_control_tokens)
    def mark_recovery_needed(self) -> None: self._mark_recovery()
    def shutdown(self, *, timeout: float = 1.0) -> bool:
        self._mark_recovery()
        close_pipe(self._incoming)
        close_pipe(self._outgoing)
        got = self._write_lock.acquire(timeout=max(0.0, timeout))
        if got:
            self._write_lock.release()
        ok = got and self.wait_closed(timeout=timeout)
        if not ok:
            self._publish_protocol("cleanup_incomplete", fatal=True)
        return ok
    def wait_closed(self, *, timeout: float | None = None) -> bool:
        if threading.current_thread() is self._reader:
            return True
        self._reader.join(timeout)
        return not self._reader.is_alive()
    def _read_loop(self) -> None:
        while True:
            try:
                line = self._incoming.readline(self._max_line_bytes + 1)
            except Exception:
                self._publish_protocol("read_error", fatal=True)
                return
            if line == b"" or line == "":
                self._publish_protocol("eof", fatal=self._awaiting())
                return
            if isinstance(line, str):
                line = line.encode("utf-8", "replace")
            if len(line) > self._max_line_bytes:
                self._publish_protocol("line_overflow", fatal=True)
                return
            try:
                raw = decode_json_frame(line)
            except ClaudeSessionWireError as exc:
                self._publish_protocol(exc.code, fatal=True)
                return
            if not self._route_raw(raw):
                return
    def _route_raw(self, raw: dict[str, Any]) -> bool:
        if self.needs_recovery():
            return False
        kind = raw.get("type") if isinstance(raw.get("type"), str) else ""
        if kind == "control_request":
            return self._publish_control_request(raw)
        if kind in _KNOWN_EVENT_TYPES:
            return self._publish_event(kind, raw)
        if kind == "control_response":
            return self._publish_control_response(raw)
        self._publish_protocol("unknown_provider_event", fatal=True)
        return False
    def _publish_event(self, kind: str, raw: dict[str, Any]) -> bool:
        if kind == "result" and not validate_result_frame(raw):
            self._publish_protocol("malformed_result", fatal=True)
            return False
        session_id = session_id_from_event(raw)
        with self._state_lock:
            mismatch = bool(session_id and self._session_id and session_id != self._session_id)
            if not mismatch:
                self._sequence += 1
                sequence = self._sequence
                if session_id:
                    self._session_id = session_id
                if kind == "result":
                    self._awaiting_result = False
        if mismatch:
            self._publish_protocol("session_id_mismatch", fatal=True)
            return False
        try:
            self._events.put_nowait(ClaudeSessionEvent(
                sequence, kind, dict(raw), session_id))
            return True
        except queue.Full:
            with self._state_lock:
                self._event_overflowed = True
            self._publish_protocol("event_overflow", fatal=True)
            return False
    def _publish_control_request(self, raw: dict[str, Any]) -> bool:
        request_id = raw.get("request_id")
        request = raw.get("request")
        if not isinstance(request_id, str) or not isinstance(request, dict):
            self._publish_protocol("malformed_control_request", fatal=True)
            return False
        subtype = request.get("subtype")
        if not isinstance(subtype, str) or subtype not in _INCOMING_CONTROL_SUBTYPES:
            self._write_control_error(request_id, f"unsupported control request subtype: {subtype}")
            self._publish_protocol("unknown_control_request", fatal=True)
            return False
        with self._state_lock:
            if request_id in self._pending_control_tokens or request_id in self._resolved_control_ids:
                duplicate = True
            else:
                duplicate = False
                self._control_token_counter += 1
                token = f"control-{self._control_token_counter}"
                self._pending_control_tokens[request_id] = token
        if duplicate:
            self._write_control_error(request_id, "duplicate control request id")
            self._publish_protocol("duplicate_control_request", fatal=True)
            return False
        control = ClaudeControlRequest(
            request_id, subtype, freeze_json(request), freeze_json(raw), token)
        try:
            self._control_requests.put_nowait(control)
            return True
        except queue.Full:
            with self._state_lock:
                self._pending_control_tokens.pop(request_id, None)
            self._write_control_error(request_id, "control request queue overflow")
            self._publish_protocol("control_request_overflow", fatal=True)
            return False
    def _publish_control_response(self, raw: dict[str, Any]) -> bool:
        try:
            matched = self._sdk_responses.resolve(raw)
        except ClaudeSessionTransportError as exc:
            self._publish_protocol(exc.code, fatal=True)
            return False
        if not matched:
            self._publish_protocol("unexpected_control_response")
        return True
    def _send_sdk_request(self, prefix: str, request: dict[str, Any], *,
                          timeout: float | None = None) -> dict[str, Any]:
        request_id, waiter = self._sdk_responses.reserve(prefix)
        frame = {"type": "control_request", "request_id": request_id, "request": request}
        try:
            self._write_raw(self._encode_frame(frame))
            return self._await_sdk_response(request_id, waiter, timeout)
        except ClaudeSessionTransportError:
            self._sdk_responses.discard(request_id)
            raise
    def _await_sdk_response(self, request_id: str, waiter,
                            timeout: float | None) -> dict[str, Any]:
        try:
            return self._sdk_responses.wait(
                request_id, waiter, self._default_timeout if timeout is None else timeout)
        except ClaudeSessionTransportError as exc:
            self._publish_protocol(exc.code, fatal=True)
            raise
    def _publish_protocol(self, kind: str, detail: str = "", *, fatal: bool = False) -> None:
        if fatal:
            self._mark_recovery()
        with self._state_lock:
            self._protocol_sequence += 1
            sequence = self._protocol_sequence
        try:
            self._protocol.put_nowait(ClaudeSessionProtocolEvent(sequence, kind, detail))
        except queue.Full:
            with self._state_lock:
                self._protocol_overflowed = True
                self._recovery_needed = True
    def _check_pending_request(self, request: ClaudeControlRequest) -> None:
        with self._state_lock:
            self._ensure_writable_locked()
            self._check_pending_request_locked(request)
    def _check_pending_request_locked(self, request: ClaudeControlRequest) -> None:
        token = self._pending_control_tokens.get(request.request_id)
        if token is None:
            code = "control_request_resolved" if request.request_id in self._resolved_control_ids else "control_request_not_pending"
            raise ClaudeSessionTransportError(code, "control request is not pending")
        if token != request.token:
            raise ClaudeSessionTransportError(
                "control_request_not_pending", "control request token did not match")
    def _write_control_error(self, request_id: str, message: str) -> None:
        try:
            self._write_raw(self._encode_frame({"type": "control_response", "response": {
                "subtype": "error", "request_id": request_id, "error": message}}))
        except ClaudeSessionTransportError:
            pass
    def _encode_frame(self, frame: dict[str, Any]) -> bytes:
        try:
            return encode_json_frame(frame)
        except ClaudeSessionWireError as exc:
            raise ClaudeSessionTransportError(exc.code, str(exc)) from exc
    def _write_raw(self, raw: bytes) -> None:
        with self._write_lock:
            with self._state_lock:
                self._ensure_writable_locked()
            self._write_raw_locked(raw, sensitive=False)
    def _write_raw_locked(self, raw: bytes, *, sensitive: bool) -> None:
        try:
            written = self._outgoing.write(raw)
            if written is None:
                written = len(raw)
            if type(written) is not int or written != len(raw):
                raise OSError("short write")
            self._outgoing.flush()
        except Exception as exc:
            self._mark_recovery()
            raise ClaudeSessionTransportError("write_failed", "short or failed write") from exc
        with self._state_lock:
            recovering = self._recovery_needed
        if recovering:
            code = "response_write_uncertain" if sensitive else "write_uncertain"
            self._publish_protocol(code, fatal=True)
            raise ClaudeSessionTransportError(code, "frame wrote during recovery")
    def _pop(self, source, timeout):
        try:
            return source.get(timeout=self._default_timeout if timeout is None else timeout)
        except queue.Empty:
            return None
    def _ensure_writable_locked(self) -> None:
        if self._recovery_needed:
            raise ClaudeSessionTransportError(
                "transport_recovery_needed", "transport needs recovery before input")
    def _awaiting(self) -> bool:
        with self._state_lock: return self._awaiting_result
    def _mark_recovery(self) -> None:
        with self._state_lock: self._recovery_needed = True
