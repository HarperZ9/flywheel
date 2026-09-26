"""Normalized views of a Codex rollout (7.6, SP-32, I13).

Each line is a JSON object with `timestamp`, optional `ordinal` and a tagged
item (`session_meta`, `response_item`, `event_msg`, `turn_context`,
`compacted` and newer kinds). Response items map to messages, tool calls,
tool results (labeled `content_trust: untrusted`) and reasoning. Reasoning
that Codex received as `encrypted_content` stays inside its stored line; the
view labels it provider-encrypted and unreadable. Unknown kinds are kept raw.
Turn ids are recovered for pairing captured turns with imported sessions.
"""
from __future__ import annotations

import json

PARSER_VERSION = "flywheel.views-codex/1"


def _text(content) -> str | None:
    if isinstance(content, str):
        return content
    parts = [c.get("text") for c in content if isinstance(c, dict)] if isinstance(
        content, list) else []
    return "".join(p for p in parts if isinstance(p, str)) or None


def _response(payload: dict) -> dict:
    kind = payload.get("type")
    if kind == "message":
        return {"kind": "message", "role": payload.get("role"),
                "text": _text(payload.get("content"))}
    if kind in ("function_call", "custom_tool_call", "local_shell_call"):
        return {"kind": "tool_call", "name": payload.get("name"),
                "input": payload.get("arguments") or payload.get("input")}
    if kind in ("function_call_output", "custom_tool_call_output"):
        return {"kind": "tool_result", "content": payload.get("output"),
                "content_trust": "untrusted"}
    if kind == "reasoning":
        encrypted = payload.get("encrypted_content") is not None
        return {"kind": "reasoning", "summary": payload.get("summary"),
                "provider_encrypted": encrypted, "readable": not encrypted}
    return {"kind": "unknown", "raw": payload}


def view_record(record) -> dict:
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        return {"kind": "unknown", "raw": record}
    if record.get("type") == "response_item":
        return _response(record["payload"])
    if record.get("type") in ("session_meta", "turn_context", "event_msg", "compacted"):
        return {"kind": "metadata", "type": record["type"]}
    return {"kind": "unknown", "raw": record}


def view_lines(data: bytes, *, depth_bound: int = 200) -> list[dict]:
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
        out.append({**view_record(record), "line": number, "parser_version": PARSER_VERSION})
    return out


def turn_ids(data: bytes) -> list[str]:
    seen: list[str] = []
    for line in data.splitlines():
        try:
            payload = json.loads(line).get("payload")
        except (ValueError, AttributeError, RecursionError):
            continue
        turn = payload.get("turn_id") if isinstance(payload, dict) else None
        if isinstance(turn, str) and turn not in seen and len(turn) <= 128:
            seen.append(turn)
    return seen
