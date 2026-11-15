"""import_source.py -- read a JSONL session file into numbered objects.

A session still being written can end in a line cut off mid-object. That line
has no newline after it, because a writer appends a line and its newline
together, so only an unterminated last line is a declared truncation. A
malformed line that ends in a newline is corruption and refuses the import,
wherever it sits.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class ImportRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    sha256: str
    lines: tuple[tuple[int, dict, str], ...]
    line_count: int
    truncated_tail: bool


def read_jsonl(path: str | Path) -> Source:
    """Parse a JSONL session file. An unterminated, malformed last line is a
    declared, reported truncation; any other malformed line refuses."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportRefused("unsupported_format", "the source is not UTF-8") from exc
    physical = text.split("\n")
    numbered = [(n, line) for n, line in enumerate(physical, start=1) if line.strip()]
    unterminated = not raw.endswith(b"\n")
    parsed, truncated = [], False
    for index, (n, line) in enumerate(numbered):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(numbered) - 1 and unterminated:
                truncated = True
                continue
            raise ImportRefused("unsupported_format", f"line {n} is not JSON") from exc
        if not isinstance(obj, dict):
            raise ImportRefused("unsupported_format", f"line {n} is not a JSON object")
        parsed.append((n, obj, line))
    return Source(Path(path).name, hashlib.sha256(raw).hexdigest(), tuple(parsed),
                  len(numbered), truncated)
