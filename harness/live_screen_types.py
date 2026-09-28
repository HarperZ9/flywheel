"""Shared live-screen DTOs and validation helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import hashlib
import re
from typing import Callable, Iterable
from urllib.parse import unquote


DELIVERY_MODES = {"sampled_image", "native_video"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}")
_KINDS = {"display", "window", "region", "synthetic"}


class LiveScreenError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise LiveScreenError(code, message)


def check_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        fail("INVALID_ID", f"{label} must be a stable identifier")
    return value


def check_path_id(value: object, label: str) -> str:
    if not isinstance(value, str):
        fail("INVALID_ID", f"{label} must be a stable identifier")
    try:
        decoded = unquote(value, errors="strict")
    except UnicodeError:
        fail("INVALID_ID", f"{label} must be a stable identifier")
    return check_id(decoded, label)


def check_model_ref(value: object) -> str:
    if not isinstance(value, str) or _MODEL.fullmatch(value) is None:
        fail("INVALID_MODEL", "model must be an exact provider model reference")
    return value


def check_bounds(value):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 4 or
            any(type(v) is not int for v in value) or value[2] <= 0 or value[3] <= 0):
        fail("INVALID_BOUNDS", "bounds must be (x, y, width, height)")
    return tuple(value)


def check_kind(kind: str) -> None:
    if kind not in _KINDS:
        fail("INVALID_SOURCE_KIND", "source kind is not supported")


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    kind: str
    label: str
    bounds: tuple[int, int, int, int] | None = None
    backend: str = "synthetic"
    available: bool = True
    unavailable_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "label": self.label,
            "bounds": self.bounds,
            "backend": self.backend,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class ScreenShareGrant:
    owner_ref: str
    destination: str
    model: str
    source_ids: tuple[str, ...]
    expires_at_ns: int


@dataclass(frozen=True)
class FrameRecord:
    session_id: str
    source_id: str
    source_sequence: int
    aggregate_sequence: int
    frame_sha256: str
    captured_at_utc: str
    captured_monotonic_ns: int
    received_at_utc: str
    width: int
    height: int
    pixel_format: str
    media_type: str
    payload: bytes = field(repr=False)
    coalesced_count: int = 0

    def identity(self) -> dict:
        return {
            "session_id": self.session_id,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "aggregate_sequence": self.aggregate_sequence,
            "frame_sha256": self.frame_sha256,
        }

    def to_event(self) -> dict:
        identity = self.identity()
        return {
            "event": "screen.frame",
            **identity,
            "frame": identity,
            "captured_at_utc": self.captured_at_utc,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "received_at_utc": self.received_at_utc,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "media_type": self.media_type,
            "coalesced_count": self.coalesced_count,
        }

    def age_ms(self, now_ns: int) -> int:
        return max(0, (now_ns - self.captured_monotonic_ns) // 1_000_000)


@dataclass(frozen=True)
class _SyntheticDescriptor:
    source_id: str
    frame_index: int
    width: int
    height: int
    pixel_format: str
    timestamp: str | None = None


@dataclass(frozen=True)
class _SyntheticFrame:
    descriptor: _SyntheticDescriptor
    payload: bytes
    media_type: str

    def read(self) -> bytes:
        return self.payload


class SyntheticCaptureSource:
    def __init__(self, source_id: str, frames: Iterable[bytes], *, width: int,
                 height: int, media_type: str = "image/png", pixel_format: str = "png"):
        self.source_id = source_id
        self._frames = list(frames)
        self.width, self.height = width, height
        self.media_type, self.pixel_format = media_type, pixel_format

    def frames(self):
        for index, payload in enumerate(self._frames):
            desc = _SyntheticDescriptor(
                self.source_id, index, self.width, self.height, self.pixel_format)
            yield _SyntheticFrame(desc, payload, self.media_type)


def frame_sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def media_type_for(pixel_format: str, explicit=None) -> str:
    if isinstance(explicit, str) and explicit:
        return explicit
    fmt = str(pixel_format or "").lower()
    if fmt == "png":
        return "image/png"
    if fmt in {"jpeg", "jpg"}:
        return "image/jpeg"
    if fmt == "webp":
        return "image/webp"
    if fmt == "gif":
        return "image/gif"
    return "application/octet-stream"


@dataclass
class RegisteredSource:
    descriptor: SourceDescriptor
    factory: Callable[[], object]


@dataclass
class LiveScreenSession:
    session_id: str
    owner_ref: str
    destination: str
    model: str
    source_ids: tuple[str, ...]
    delivery_mode: str
    expires_at_ns: int
    buffer_frames_per_source: int
    max_frame_bytes: int
    state: str = "created"
    buffers: dict[str, deque] = field(default_factory=dict)
    capture_sources: dict[str, object] = field(default_factory=dict)
    iterators: dict[str, object] = field(default_factory=dict)
    source_sequences: dict[str, int] = field(default_factory=dict)
    dropped_frames: dict[str, int] = field(default_factory=dict)
    events: deque = field(default_factory=deque)
    aggregate_sequence: int = 0
    reserved_buffer_bytes: int = 0
    cleanup_errors: list[str] = field(default_factory=list)
