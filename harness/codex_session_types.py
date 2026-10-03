"""Shared types for Codex native session transport/client modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SERVER_REQUEST_OVERFLOW = -32000
INTERNAL_ERROR = -32603
MISSING = object()


class CodexSessionTransportError(RuntimeError):
    """Sanitized transport failure. Raw peer text is never echoed."""

    def __init__(
            self, code: str, method: str | None = None, *,
            error_code: int | None = None):
        self.code = code
        self.method = method
        self.error_code = error_code
        suffix = f" ({error_code})" if error_code is not None else ""
        name = method or "codex session transport"
        super().__init__(f"{name} failed: {code}{suffix}")


@dataclass(frozen=True)
class CodexNotification:
    sequence: int
    method: str
    params: Any = field(default_factory=dict)


@dataclass(frozen=True)
class CodexProtocolEvent:
    kind: str
    request_id: int | str | None = None


@dataclass
class CodexServerRequest:
    id: int | str
    method: str
    params: Any
    sequence: int
    _owner: object = field(repr=False)
    _resolved: bool = field(default=False, init=False, repr=False)
    _token: object | None = field(default=None, init=False, repr=False)
