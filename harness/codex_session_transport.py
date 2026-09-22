from __future__ import annotations
import queue
import threading
import time
from typing import Any
from .codex_session_io import acquire_lock, close_stream, write_all
from .codex_session_types import INTERNAL_ERROR, MISSING, SERVER_REQUEST_OVERFLOW, CodexNotification, CodexProtocolEvent, CodexServerRequest, CodexSessionTransportError
from .codex_session_wire import classify, encode, failure, loads, notification, readline_bounded, request, success
class CodexSessionTransport:
    def __init__(
            self, outgoing, incoming, *, default_timeout: float = 10.0,
            notification_queue_size: int = 256,
            server_request_queue_size: int = 64,
            protocol_event_queue_size: int = 256,
            max_frame_bytes: int = 1024 * 1024,
            close_timeout: float = 0.5):
        self._outgoing = outgoing
        self._incoming = incoming
        self.default_timeout = default_timeout
        self.max_frame_bytes = max_frame_bytes
        self.close_timeout = close_timeout
        self._next_id = 0
        self._next_sequence = 0
        self._pending: dict[int | str, str] = {}
        self._responses: dict[int | str, dict] = {}
        self._server_pending: dict[int | str, object] = {}
        self._condition = threading.Condition()
        self._write_lock = threading.Lock()
        self._closed = False
        self._cleanup_complete = False
        self._failure: CodexSessionTransportError | None = None
        self._notification_overflowed = False
        self._server_request_overflowed = False
        self._server_requests_invalidated = False
        self._event_loss = False
        q = lambda size: queue.Queue(maxsize=max(1, int(size)))
        self._notifications: queue.Queue[CodexNotification] = q(notification_queue_size)
        self._server_requests: queue.Queue[CodexServerRequest] = q(server_request_queue_size)
        self._events: queue.Queue[CodexProtocolEvent] = q(protocol_event_queue_size)
        self._reader = threading.Thread(target=self._read_loop, name="codex-session-reader", daemon=True)
        self._reader.start()
    @property
    def closed(self) -> bool:
        return self._closed
    def request(self, method: str, params: Any = None, *, timeout: float | None = None) -> Any:
        request_id = self._reserve(method)
        try:
            self._send(request(request_id, method, params), method)
        except CodexSessionTransportError:
            self._drop_client(request_id)
            raise
        except Exception as exc:
            self._drop_client(request_id)
            self._mark_failed("write_failed", request_id=request_id)
            raise CodexSessionTransportError("write_failed", method) from exc
        return self._wait(method, request_id, timeout)
    def notify(self, method: str, params: Any = None) -> None:
        self._send(notification(method, params), method)
    def pop_notification(self, *, timeout: float = 0.0) -> CodexNotification | None:
        return self._pop(self._notifications, timeout)
    def pop_server_request(self, *, timeout: float = 0.0) -> CodexServerRequest | None:
        return self._pop(self._server_requests, timeout)
    def pop_protocol_event(self, *, timeout: float = 0.0) -> CodexProtocolEvent | None:
        return self._pop(self._events, timeout)
    def notification_overflowed(self) -> bool:
        return self._notification_overflowed
    def server_request_overflowed(self) -> bool:
        return self._server_request_overflowed
    def reply(self, server_request: CodexServerRequest, *, result: Any = MISSING, error: dict | None = None) -> None:
        self._send_reply(server_request, self._encode_reply(self._prepare_reply(server_request, result, error)))
    def close(self, *, timeout: float | None = None) -> bool:
        self._close_state("closed")
        return self._cleanup(self.close_timeout if timeout is None else timeout)
    def _prepare_reply(self, server_request, result: Any, error: dict | None) -> dict:
        if not isinstance(server_request, CodexServerRequest):
            raise CodexSessionTransportError("request_owner_mismatch")
        if server_request._owner is not self:
            raise CodexSessionTransportError("request_owner_mismatch")
        if (result is MISSING) == (error is None):
            raise CodexSessionTransportError("invalid_reply")
        with self._condition:
            self._check_reply_ready(server_request)
        if error is None:
            return success(server_request.id, result)
        code = error.get("code", INTERNAL_ERROR)
        if not isinstance(code, int) or isinstance(code, bool):
            raise CodexSessionTransportError("invalid_reply")
        return failure(server_request.id, code, str(error.get("message", "request failed")), error.get("data"))
    def _reserve(self, method: str) -> int:
        with self._condition:
            self._check_open(method)
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = method
            return request_id
    def _send(self, message: dict, method: str | None = None) -> None:
        self._send_data(encode(message), method)
    def _wait(self, method: str, request_id: int | str, timeout: float | None) -> Any:
        deadline = time.monotonic() + (self.default_timeout if timeout is None else timeout)
        with self._condition:
            while request_id not in self._responses:
                if self._failure is not None:
                    self._pending.pop(request_id, None)
                    raise CodexSessionTransportError(self._failure.code, method)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._pending.pop(request_id, None)
                    raise CodexSessionTransportError("timeout", method)
                self._condition.wait(min(remaining, 0.05))
            message = self._responses.pop(request_id)
            self._pending.pop(request_id, None)
        if "error" in message:
            raise CodexSessionTransportError("peer_error", method, error_code=message["error"].get("code"))
        return message["result"]
    def _read_loop(self) -> None:
        while True:
            try:
                line = readline_bounded(self._incoming, self.max_frame_bytes)
            except Exception:
                self._fail("read_failed")
                return
            if not line:
                self._fail("eof")
                return
            if len(line) > self.max_frame_bytes:
                self._fail("frame_too_large")
                return
            try:
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                message = loads(text)
                kind = classify(message)
            except (UnicodeDecodeError, TypeError, ValueError):
                self._fail("malformed_frame")
                return
            self._route(message, kind)
    def _send_reply(self, server_request: CodexServerRequest, data: bytes) -> None:
        with self._write_lock:
            with self._condition:
                self._check_reply_ready(server_request)
            try:
                write_all(self._outgoing, data)
            except Exception as exc:
                self._mark_failed("write_failed", request_id=server_request.id)
                raise CodexSessionTransportError("write_failed") from exc
            with self._condition:
                self._commit_reply(server_request)
    def _send_data(self, data: bytes, method: str | None = None) -> None:
        with self._write_lock:
            with self._condition:
                self._check_open(method)
            try:
                write_all(self._outgoing, data)
            except Exception as exc:
                self._mark_failed("write_failed")
                raise CodexSessionTransportError("write_failed", method) from exc
            with self._condition:
                self._check_open(method)
    def _encode_reply(self, message: dict) -> bytes:
        try:
            return encode(message)
        except (TypeError, ValueError, OverflowError) as exc:
            raise CodexSessionTransportError("invalid_reply") from exc
    def _check_reply_ready(self, server_request: CodexServerRequest) -> None:
        self._check_open()
        if server_request._resolved:
            raise CodexSessionTransportError("request_resolved")
        if self._event_loss or self._notification_overflowed:
            raise CodexSessionTransportError("event_loss")
        if self._server_requests_invalidated:
            raise CodexSessionTransportError("server_requests_invalidated")
        token = self._server_pending.get(server_request.id)
        if token is None or token is not server_request._token:
            raise CodexSessionTransportError("request_not_pending")
    def _commit_reply(self, server_request: CodexServerRequest) -> None:
        self._check_reply_ready(server_request)
        server_request._resolved = True
        self._server_pending.pop(server_request.id, None)
    def _route(self, message: dict, kind: str) -> None:
        if kind in ("response", "failure"):
            self._settle(message)
        elif kind == "request":
            self._queue_server_request(message)
        else:
            self._queue_notification(message)
    def _settle(self, message: dict) -> None:
        request_id = message["id"]
        with self._condition:
            if request_id not in self._pending:
                self._put_event("orphan_response", request_id=request_id)
            elif request_id in self._responses:
                self._put_event("duplicate_response", request_id=request_id)
            else:
                self._responses[request_id] = message
                self._condition.notify_all()
    def _queue_notification(self, message: dict) -> None:
        note = CodexNotification(self._sequence(), message["method"], message.get("params") or {})
        try:
            self._notifications.put_nowait(note)
        except queue.Full:
            self._notification_overflowed = True
            self._event_loss = True
            self._put_event("notification_overflow")
    def _queue_server_request(self, message: dict) -> None:
        request_id = message["id"]
        req = CodexServerRequest(request_id, message["method"], message.get("params") or {}, self._sequence(), self)
        req._token = object()
        refusal = None
        with self._condition:
            if self._server_requests_invalidated or self._event_loss:
                refusal = self._refusal(request_id, "server_request_rejected", "server requests invalidated")
            elif request_id in self._server_pending:
                self._server_requests_invalidated = True
                refusal = self._refusal(request_id, "duplicate_server_request", "duplicate server request")
            else:
                self._server_pending[request_id] = req._token
                try:
                    self._server_requests.put_nowait(req)
                except queue.Full:
                    self._server_pending.pop(request_id, None)
                    self._server_request_overflowed = True
                    self._server_requests_invalidated = True
                    refusal = self._refusal(request_id, "server_request_overflow", "server request overflow")
        if refusal is not None:
            try:
                self._send(refusal)
            except Exception:
                self._put_event("write_failed", request_id=request_id)
    def _refusal(self, request_id: int | str, kind: str, message: str) -> dict:
        self._put_event(kind, request_id=request_id)
        return failure(request_id, SERVER_REQUEST_OVERFLOW, message)
    def _cleanup(self, timeout: float | None) -> bool:
        with self._condition:
            if self._cleanup_complete:
                return True
        deadline = None if timeout is None else time.monotonic() + timeout
        close_stream(self._outgoing)
        close_stream(self._incoming)
        if not acquire_lock(self._write_lock, self._remaining(deadline)):
            self._put_event("cleanup_incomplete")
            return False
        try:
            close_stream(self._outgoing)
            close_stream(self._incoming)
        finally:
            self._write_lock.release()
        ok = self.wait_closed(timeout=self._remaining(deadline))
        if ok:
            with self._condition:
                self._cleanup_complete = True
        else:
            self._put_event("cleanup_incomplete")
        return ok
    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        return None if deadline is None else max(0.0, deadline - time.monotonic())
    def _sequence(self) -> int:
        with self._condition:
            self._next_sequence += 1
            return self._next_sequence
    def _put_event(self, kind: str, *, request_id: int | str | None = None) -> None:
        try:
            self._events.put_nowait(CodexProtocolEvent(kind, request_id))
        except queue.Full:
            self._event_loss = True
    def _fail(self, code: str) -> None:
        self._put_event(code)
        self._close_state(code)
        close_stream(self._outgoing)
        close_stream(self._incoming)
    def _mark_failed(self, code: str, *, request_id: int | str | None = None) -> None:
        self._put_event(code, request_id=request_id)
        self._close_state(code)
        close_stream(self._outgoing)
        close_stream(self._incoming)
    def _close_state(self, code: str) -> None:
        with self._condition:
            if self._failure is None:
                self._failure = CodexSessionTransportError(code)
            self._closed = True
            self._condition.notify_all()
    def wait_closed(self, timeout: float | None = None) -> bool:
        if threading.current_thread() is self._reader:
            return True
        self._reader.join(timeout)
        return not self._reader.is_alive()
    def _check_open(self, method: str | None = None) -> None:
        if self._failure is not None:
            raise CodexSessionTransportError(self._failure.code, method)
        if self._closed:
            raise CodexSessionTransportError("closed", method)
    def _drop_client(self, request_id: int | str) -> None:
        with self._condition:
            self._pending.pop(request_id, None)
            self._responses.pop(request_id, None)
    @staticmethod
    def _pop(source: queue.Queue, timeout: float):
        try: return source.get(timeout=timeout)
        except queue.Empty: return None
