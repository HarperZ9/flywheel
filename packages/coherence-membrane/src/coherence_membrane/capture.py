"""The frame-handoff contract -- the agnostic spine of live perception.

The single most important architectural decision in this package: the membrane
does NOT reach into a graphics API to grab frames.  It would then be coupled to
D3D11, and have to chase D3D12, Vulkan, Metal, and whatever comes next, forever.
Instead the dependency is INVERTED -- a producer (an engine, a creative tool, a
capture shim) hands the membrane a Frame, and the membrane only ever sees bytes
plus a descriptor.  This contract never changes when a graphics API does.

  producer (owns the version-coupled grab) ──Frame──▶ CaptureSource ──▶ membrane

A `CaptureSource` is anything that yields Frames.  Two portable, stdlib-only
sources ship here:
  * DirectoryFrameSource -- frames a producer writes to a folder (zero deps; any
    tool that can write a PNG can integrate),
  * CallableFrameSource -- frames pulled from a producer callback (an engine shim
    drives it directly).
Heavy, platform-specific grabbers (screen capture, a D3D12 present-hook) are
out-of-core plugins that implement the same `frames()` iterator and are never
imported by the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class FrameDescriptor:
    """API-agnostic metadata about a frame.  All graphics-API-specific detail
    collapses into these neutral fields, so the membrane stays agnostic."""

    source_id: str
    frame_index: int
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None  # e.g. "png", "rgba8", "raw"
    colorspace: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "frame_index": self.frame_index,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "colorspace": self.colorspace,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class Frame:
    """A frame handed to the membrane: a descriptor plus either inline bytes or a
    path to read.  `read()` returns the raw bytes either way."""

    descriptor: FrameDescriptor
    payload: bytes | None = None
    path: str | None = None

    def read(self) -> bytes:
        if self.payload is not None:
            return self.payload
        if self.path is not None:
            with open(self.path, "rb") as f:
                return f.read()
        return b""


@runtime_checkable
class CaptureSource(Protocol):
    """Anything that yields Frames.  The membrane's only coupling to the world."""

    def frames(self) -> Iterator[Frame]: ...


class DirectoryFrameSource:
    """Yield frames a producer writes into a directory (sorted by name).

    Zero dependencies: any tool that can write an image file can feed the
    membrane.  This snapshots the matching files at call time; for an always-on
    watch, wrap it in a polling loop (the producer's cadence, not the core's).
    """

    def __init__(self, directory, pattern: str = "*.png", source_id: str | None = None):
        self.directory = Path(directory)
        self.pattern = pattern
        self.source_id = source_id or str(self.directory)

    def frames(self) -> Iterator[Frame]:
        for index, p in enumerate(sorted(self.directory.glob(self.pattern))):
            if not p.is_file():
                continue
            fmt = p.suffix.lstrip(".").lower() or None
            yield Frame(
                descriptor=FrameDescriptor(
                    source_id=self.source_id, frame_index=index, pixel_format=fmt
                ),
                path=str(p),
            )


class CallableFrameSource:
    """Yield frames pulled from a producer callable.

    The callable returns the next payload (bytes) or None to stop.  An engine
    shim implements `producer()` and the membrane consumes -- the grab logic
    stays entirely on the producer side.
    """

    def __init__(self, producer: Callable[[], bytes | None], *, source_id: str = "callable",
                 pixel_format: str | None = None):
        self.producer = producer
        self.source_id = source_id
        self.pixel_format = pixel_format

    def frames(self) -> Iterator[Frame]:
        index = 0
        while True:
            payload = self.producer()
            if payload is None:
                return
            yield Frame(
                descriptor=FrameDescriptor(
                    source_id=self.source_id, frame_index=index,
                    pixel_format=self.pixel_format,
                ),
                payload=payload,
            )
            index += 1


class IterableFrameSource:
    """Wrap an iterable of (bytes) or Frame objects as a CaptureSource -- handy for
    tests and for producers that already have a sequence in hand."""

    def __init__(self, items: Iterable, *, source_id: str = "iterable",
                 pixel_format: str | None = None):
        self.items = items
        self.source_id = source_id
        self.pixel_format = pixel_format

    def frames(self) -> Iterator[Frame]:
        for index, item in enumerate(self.items):
            if isinstance(item, Frame):
                yield item
            else:
                yield Frame(
                    descriptor=FrameDescriptor(
                        source_id=self.source_id, frame_index=index,
                        pixel_format=self.pixel_format,
                    ),
                    payload=bytes(item),
                )
