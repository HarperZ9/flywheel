"""Normalized views of a Claude Code transcript (7.6, SP-32, I13).

Known record types map to normalized entries (message text, tool call, tool
result, reasoning); anything else is kept raw with kind `unknown`, since the
entry format is internal to Claude Code and changes between versions. Tool
results carry `content_trust: untrusted`, the label canon's records use, so
content a tool read is never mistaken for the owner's instructions when it
re-enters a model. A view never changes stored bytes.
"""
from __future__ import annotations

import json

PARSER_VERSION = "flywheel.views-claude/1"


def _blocks(role: str, content) -> list[dict]:
    if isinstance(content, str):
        return [{"kind": "message", "role": role, "text": content}]
    out = []
    for block in content if isinstance(content, list) else []:
        kind = block.get("type") if isinstance(block, dict) else None
        if kind == "text":
            out.append({"kind": "message", "role": role, "text": block.get("text")})
        elif kind == "tool_use":
            out.append({"kind": "tool_call", "role": role, "name": block.get("name"),
                        "input": block.get("input")})
        elif kind == "tool_result":
            out.append({"kind": "tool_result", "role": role, "content": block.get("content"),
                        "content_trust": "untrusted"})
        elif kind in ("thinking", "redacted_thinking"):
            out.append({"kind": "reasoning", "role": role, "text": block.get("thinking")})
        else:
            out.append({"kind": "unknown", "raw": block})
    return out


def view_record(record) -> list[dict]:
    if not isinstance(record, dict):
        return [{"kind": "unknown", "raw": record}]
    message = record.get("message")
    if record.get("type") in ("user", "assistant") and isinstance(message, dict):
        return _blocks(message.get("role") or record["type"], message.get("content"))
    return [{"kind": "unknown", "raw": record}]


def view_lines(data: bytes, *, depth_bound: int = 200) -> list[dict]:
    """Every line as normalized entries; unparseable lines kept as such."""
    from .trace_import_lines import _depth
    out = []
    for number, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if _depth(record, depth_bound) > depth_bound:
                raise ValueError("too deep")
        except (ValueError, RecursionError, UnicodeDecodeError):
            out.append({"kind": "unparseable", "line": number})
            continue
        for entry in view_record(record):
            out.append({**entry, "line": number, "parser_version": PARSER_VERSION})
    return out
