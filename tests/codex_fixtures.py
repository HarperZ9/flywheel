"""A synthetic Codex home for the import tests: plain, archived, compressed
and live rollouts, a thread-history database, and the stores Codex keeps
that the importer names and does not read. No real history."""
from __future__ import annotations

import json
from pathlib import Path

from import_fixtures import age_tree

T1 = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
T2 = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a6c"
T3 = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a7d"
T4 = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a8e"
FAKE_MAGIC = b"ZSTDFAKE"


def _lines(*records) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


def rollout(thread: str) -> bytes:
    return _lines(
        {"timestamp": "2026-09-20T10:11:12Z", "type": "session_meta",
         "payload": {"id": thread, "cwd": "C:/work/demo"}},
        {"timestamp": "2026-09-20T10:11:13Z", "type": "turn_context",
         "payload": {"turn_id": "turn-1", "model": "synthetic"}},
        {"timestamp": "2026-09-20T10:11:14Z", "type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "codex prompt text"}]}},
        {"timestamp": "2026-09-20T10:11:15Z", "type": "response_item", "payload": {
            "type": "function_call", "name": "shell", "arguments": "{\"cmd\": \"ls\"}"}},
        {"timestamp": "2026-09-20T10:11:16Z", "type": "response_item", "payload": {
            "type": "function_call_output", "output": "a.txt"}},
        {"timestamp": "2026-09-20T10:11:17Z", "type": "response_item", "payload": {
            "type": "reasoning", "summary": [], "encrypted_content": "gAAAAB-opaque-blob"}},
        {"timestamp": "2026-09-20T10:11:18Z", "type": "event_msg",
         "payload": {"type": "token_count", "turn_id": "turn-1"}},
        {"timestamp": "2026-09-20T10:11:19Z", "type": "brand_new_kind", "payload": {}},
    )


def codex_tree(base: Path) -> Path:
    root = base / "codex"
    day = root / "sessions" / "2026" / "09" / "20"
    day.mkdir(parents=True)
    (day / f"rollout-2026-09-20T10-11-12-{T1}.jsonl").write_bytes(rollout(T1))
    (root / "archived_sessions").mkdir()
    (root / "archived_sessions" / f"rollout-2026-08-01T09-00-00-{T2}.jsonl").write_bytes(
        rollout(T2))
    older = root / "sessions" / "2026" / "09" / "13"
    older.mkdir(parents=True)
    (older / f"rollout-2026-09-13T08-00-00-{T3}.jsonl.zst").write_bytes(
        FAKE_MAGIC + rollout(T3))
    live = root / "sessions" / "2026" / "09" / "21"
    live.mkdir(parents=True)
    (live / f"rollout-2026-09-21T07-00-00-{T4}.jsonl").write_bytes(rollout(T4))
    (root / "thread-writer-locks").mkdir()
    (root / "thread-writer-locks" / T4).write_bytes(b"")
    (root / "thread_history_1.sqlite").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    (root / "history.jsonl").write_bytes(_lines({"text": "an old codex prompt"}))
    (root / "session_index.jsonl").write_bytes(_lines({"id": T1}))
    age_tree(root, seconds=300)
    return root


class FakeDecompressor:
    """Stands in for compression.zstd: strips the fake magic, or, as a bomb,
    returns 1 MiB of output for every call and never asks for input."""

    def __init__(self, bomb: bool = False) -> None:
        self.bomb, self.eof, self.needs_input, self.seen = bomb, False, True, b""

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        if self.bomb:
            self.needs_input = False
            return b"x" * (1024 * 1024)
        self.seen += data
        self.needs_input = True
        if self.seen.startswith(FAKE_MAGIC):
            out, self.seen = self.seen[len(FAKE_MAGIC):], FAKE_MAGIC
            return out
        return b""


class FakeZstd:
    def __init__(self, bomb: bool = False) -> None:
        self.bomb = bomb

    def ZstdDecompressor(self):  # noqa: N802  (the stdlib module's name)
        return FakeDecompressor(self.bomb)
