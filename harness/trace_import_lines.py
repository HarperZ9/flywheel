"""Line accounting for imported JSONL while it streams (7.6, SP-29).

Each complete line is classified: `parsed` with its record type counted
(unknown types included, since the stored bytes keep them), `oversized` when
it passes the line bound (the bytes are stored anyway; only the view skips
it), or `unparseable` when it is not JSON or nests deeper than the view bound
(RecursionError is caught and classified the same way). A redaction index
records, per line, how many hits each credential rule found; the text itself
is never copied into the index.
"""
from __future__ import annotations

import json
import os


def _depth(value, limit: int) -> int:
    deepest, stack = 0, [(value, 1)]
    while stack:
        item, level = stack.pop()
        deepest = max(deepest, level)
        if deepest > limit:
            return deepest
        if isinstance(item, dict):
            stack.extend((v, level + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, level + 1) for v in item)
    return deepest


class LineAnalyzer:
    def __init__(self, bound: int, depth_bound: int = 200, redact: bool = True,
                 turn_ids: bool = False) -> None:
        self.bound, self.depth_bound, self.redact = bound, depth_bound, redact
        self.turn_ids: list[str] | None = [] if turn_ids else None
        self.carry, self.skipping, self.number = b"", False, 0
        self.kinds = {"parsed": 0, "oversized": 0, "unparseable": 0}
        self.types: dict[str, int] = {}
        self.index: list[dict] = []
        self.key = os.urandom(32)

    def feed(self, chunk: bytes) -> None:
        data = self.carry + chunk
        *lines, self.carry = data.split(b"\n")
        for line in lines:
            if self.skipping:
                self.skipping = False
                continue
            self._line(line)
        if len(self.carry) > self.bound and not self.skipping:
            self.kinds["oversized"] += 1
            self.number += 1
            self.carry, self.skipping = b"", True
        elif self.skipping:
            self.carry = b""

    def finish(self) -> dict:
        if self.carry and not self.skipping:
            self._line(self.carry)
        self.carry = b""
        stats = {"lines": self.number, "line_kinds": dict(self.kinds),
                 "record_types": dict(self.types)}
        if self.turn_ids is not None:
            stats["turn_ids"] = list(self.turn_ids)
        return stats

    def _line(self, line: bytes) -> None:
        self.number += 1
        if len(line) > self.bound:
            self.kinds["oversized"] += 1
            return
        if not line.strip():
            return
        try:
            value = json.loads(line)
            if _depth(value, self.depth_bound) > self.depth_bound:
                raise ValueError("too deep")
        except (ValueError, RecursionError, UnicodeDecodeError):
            self.kinds["unparseable"] += 1
            return
        self.kinds["parsed"] += 1
        kind = value.get("type") if isinstance(value, dict) else None
        name = kind if isinstance(kind, str) and len(kind) <= 64 else "untyped"
        self.types[name] = self.types.get(name, 0) + 1
        payload = value.get("payload") if isinstance(value, dict) else None
        turn = payload.get("turn_id") if isinstance(payload, dict) else None
        wanted = self.turn_ids is not None and isinstance(turn, str) and len(turn) <= 128
        if wanted and turn not in self.turn_ids:
            self.turn_ids.append(turn)
        if self.redact:
            self._redaction(line)

    def _redaction(self, line: bytes) -> None:
        from .trace_redact import ScanBudgetExceeded, redact_line
        try:
            _, counts = redact_line(line.decode("utf-8", "replace"), key=self.key)
        except ScanBudgetExceeded:
            counts = {"SCAN_BUDGET_EXCEEDED": 1}
        if counts:
            self.index.append({"line": self.number, "rules": counts})
