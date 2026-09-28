"""Streaming zstd for compressed Codex rollouts, under bounds (7.6, N-18, SP-29).

Codex compresses rollouts older than seven days to `.jsonl.zst` behind a
feature flag. They are read with `compression.zstd` on Python 3.14 and later,
else the optional `backports.zstd`, else not at all: each file is then named
UNSUPPORTED_COMPRESSION with its size. Output is produced at most 1 MiB at a
time and never written to disk decompressed; the ratio (200:1) is checked as
it streams, and total output is capped (2 GiB), so a bomb stops early with
INPUT_BOUND:ratio or INPUT_BOUND:decompressed.
"""
from __future__ import annotations

RATIO = 200
MAX_OUTPUT = 2 * 1024 * 1024 * 1024
_PIECE = 1024 * 1024


class InputBound(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(f"INPUT_BOUND:{kind}")
        self.code = f"INPUT_BOUND:{kind}"


def module():
    try:
        from compression import zstd
        return zstd
    except ImportError:
        pass
    try:
        from backports import zstd
        return zstd
    except ImportError:
        return None


def available() -> bool:
    return module() is not None


class Stream:
    """Feed compressed chunks; get decompressed pieces through `emit`."""

    def __init__(self, emit, *, ratio: int = RATIO, max_output: int = MAX_OUTPUT) -> None:
        zstd = module()
        if zstd is None:
            raise InputBound("unsupported")
        self.decompressor = zstd.ZstdDecompressor()
        self.emit, self.ratio, self.max_output = emit, ratio, max_output
        self.consumed = self.produced = 0

    def _check(self) -> None:
        if self.produced > self.max_output:
            raise InputBound("decompressed")
        if self.produced > max(self.consumed, 4096) * self.ratio:
            raise InputBound("ratio")

    def feed(self, chunk: bytes) -> None:
        self.consumed += len(chunk)
        data = chunk
        while True:
            piece = self.decompressor.decompress(data, max_length=_PIECE)
            data = b""
            self.produced += len(piece)
            self._check()
            if piece:
                self.emit(piece)
            if self.decompressor.eof or self.decompressor.needs_input:
                return
