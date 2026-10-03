"""SDK control response matching for Claude stream-json sessions."""
from __future__ import annotations

import queue
import threading
from typing import Any


class ClaudeSessionTransportError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ControlResponseTable:
    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0
        self._pending: dict[str, queue.Queue] = {}

    def reserve(self, prefix: str) -> tuple[str, queue.Queue]:
        waiter: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._counter += 1
            request_id = f"flywheel-{prefix}-{self._counter}"
            self._pending[request_id] = waiter
        return request_id, waiter

    def resolve(self, raw: dict[str, Any]) -> bool:
        response = raw.get("response")
        if not isinstance(response, dict):
            raise ClaudeSessionTransportError(
                "malformed_control_response", "control response is malformed")
        request_id = response.get("request_id")
        if not isinstance(request_id, str):
            raise ClaudeSessionTransportError(
                "malformed_control_response", "control response is malformed")
        with self._lock:
            waiter = self._pending.get(request_id)
        if waiter is None:
            return False
        try:
            waiter.put_nowait(dict(response))
        except queue.Full:
            raise ClaudeSessionTransportError(
                "duplicate_control_response", "control response was duplicated")
        return True

    def wait(self, request_id: str, waiter: queue.Queue, timeout: float | None) -> dict[str, Any]:
        try:
            response = waiter.get(timeout=timeout)
        except queue.Empty as exc:
            self.discard(request_id)
            raise ClaudeSessionTransportError(
                "control_response_timeout", "control response did not arrive") from exc
        self.discard(request_id)
        subtype = response.get("subtype")
        if subtype == "success" and isinstance(response.get("response"), dict):
            return dict(response["response"])
        if subtype == "error":
            raise ClaudeSessionTransportError(
                "control_response_error", "control request failed")
        raise ClaudeSessionTransportError(
            "malformed_control_response", "control response is malformed")

    def discard(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(request_id, None)


def require_positive(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ClaudeSessionTransportError(
            "invalid_queue_size", f"{name} must be a positive integer")


def close_pipe(pipe) -> None:
    close = getattr(pipe, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
