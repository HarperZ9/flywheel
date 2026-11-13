"""Read-only observer for one Claude Code transcript (JSONL).

Layout, as observed on 2026-09-10 against Claude Code transcripts under
~/.claude/projects/<cwd-slug>/<session-uuid>.jsonl: every line is a JSON
object with a top-level "type". Conversation lines ("user", "assistant")
carry sessionId, cwd, version, gitBranch, timestamp, uuid, parentUuid and a
"message" object; assistant messages carry "model". Bookkeeping lines
("custom-title", "last-prompt", "bridge-session", "attachment", "system",
"queue-operation") carry their own keys. Text is never copied out. Each
string of interest becomes a length plus SHA-256.
"""
from __future__ import annotations

from collections import Counter

from .peer_session_io import (DEFAULT_HEAD_BYTES, DEFAULT_TAIL_BYTES, age_seconds, iter_jsonl,
                              public_window, read_windows, text_digest)
from .peer_session_types import (AGREED, HARNESS_CLAUDE, activity_state, base_record,
                                 bounded_counts, bucket, consistent, label)

CONVERSATION_TYPES = ("user", "assistant")
IDENTITY_KEYS = ("sessionId", "cwd", "version", "gitBranch", "entrypoint", "userType")
RECORD_TYPES = ("user", "assistant", "system", "summary", "custom-title", "last-prompt",
                "bridge-session", "attachment", "queue-operation", "progress",
                "file-history-snapshot", "compact-boundary")
BLOCK_TYPES = ("text", "text_string", "thinking", "redacted_thinking", "tool_use", "tool_result",
               "image", "document", "server_tool_use", "web_search_tool_result")
STOP_REASONS = ("end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
                "model_context_window_exceeded")


def _blocks(message: object) -> Counter:
    counts: Counter = Counter()
    if type(message) is not dict:
        return counts
    content = message.get("content")
    if type(content) is str:
        counts["text_string"] += 1
    elif type(content) is list:
        for block in content:
            kind = block.get("type") if type(block) is dict else None
            counts[bucket(kind, BLOCK_TYPES)] += 1
    return counts


def _tool_names(message: object) -> list[str]:
    names = []
    if type(message) is dict and type(message.get("content")) is list:
        for block in message["content"]:
            if (type(block) is dict and block.get("type") == "tool_use"
                    and type(block.get("name")) is str):
                names.append(block["name"])
    return names


def _prompt_text(rec: dict) -> str | None:
    message = rec.get("message")
    content = message.get("content") if type(message) is dict else None
    if type(content) is str:
        return content
    if type(content) is list and content and type(content[0]) is dict:
        first = content[0]
        if first.get("type") == "text" and type(first.get("text")) is str:
            return first["text"]
    return None


def _last_user_prompt(records: list[tuple[int, dict]]) -> dict | None:
    for _offset, rec in reversed(records):
        if rec.get("type") != "user" or rec.get("isSidechain") is True:
            continue
        text = _prompt_text(rec)
        if text is None:
            continue
        return {"timestamp": rec.get("timestamp") if type(rec.get("timestamp")) is str else None,
                "text_ref": text_digest(text),
                "uuid": rec.get("uuid") if type(rec.get("uuid")) is str else None}
    return None


def _last_assistant(records: list[tuple[int, dict]]) -> dict | None:
    """The last main-thread assistant turn. Subagent (sidechain) turns are skipped
    so a spawned agent's reply is not reported as the session's own last answer."""
    for _offset, rec in reversed(records):
        if rec.get("type") != "assistant" or rec.get("isSidechain") is True:
            continue
        message = rec.get("message") if type(rec.get("message")) is dict else {}
        stop = message.get("stop_reason")
        return {"timestamp": rec.get("timestamp") if type(rec.get("timestamp")) is str else None,
                "model": label(message.get("model")),
                "stop_reason": None if stop is None else bucket(stop, STOP_REASONS),
                "block_types": sorted(_blocks(message))}
    return None


def _summarize(records: list[tuple[int, dict]]) -> dict:
    types: Counter = Counter()
    blocks: Counter = Counter()
    tools: Counter = Counter()
    identity = {key: [] for key in IDENTITY_KEYS}
    models, timestamps, sidechain, titles, last_prompt = [], [], 0, [], None
    for _offset, rec in records:
        kind = rec.get("type")
        types[bucket(kind, RECORD_TYPES)] += 1
        if kind == "custom-title" and type(rec.get("customTitle")) is str:
            titles.append(text_digest(rec["customTitle"]))
        if kind == "last-prompt" and type(rec.get("lastPrompt")) is str:
            last_prompt = text_digest(rec["lastPrompt"])
        if kind not in CONVERSATION_TYPES:
            continue
        for key in IDENTITY_KEYS:
            if type(rec.get(key)) is str:
                identity[key].append(rec[key])
        if rec.get("isSidechain") is True:
            sidechain += 1
        if type(rec.get("timestamp")) is str:
            timestamps.append(rec["timestamp"])
        message = rec.get("message")
        for block, n in _blocks(message).items():
            blocks[f"{kind}:{block}"] += n
        if kind == "assistant":
            for name in _tool_names(message):
                tools[label(name)] += 1
            if type(message) is dict and type(message.get("model")) is str:
                models.append(label(message["model"]))
    return {"record_type_counts": bounded_counts(types),
            "content_block_counts": bounded_counts(blocks),
            "tool_use_counts": bounded_counts(tools),
            "sidechain_records": sidechain,
            "identity": {key: consistent(values) for key, values in identity.items()},
            "models_reported": sorted(set(models)),
            "first_timestamp_in_window": min(timestamps) if timestamps else None,
            "last_timestamp_in_window": max(timestamps) if timestamps else None,
            "custom_title_ref": titles[-1] if titles else None,
            "last_prompt_ref": last_prompt}


def observe_claude_transcript(path, *, observed_at: str, head_bytes: int = DEFAULT_HEAD_BYTES,
                              tail_bytes: int = DEFAULT_TAIL_BYTES) -> dict:
    """Describe one transcript from its head and tail windows. Never writes."""
    windows = read_windows(path, head_bytes=head_bytes, tail_bytes=tail_bytes)
    head_records, head_report = iter_jsonl(windows["head"]["_bytes"])
    if windows["source"]["tail_window_is_head_window"]:
        tail_records, tail_report = head_records, head_report
    else:
        tail_records, tail_report = iter_jsonl(windows["tail"]["_bytes"])
    record = base_record(HARNESS_CLAUDE, observed_at=observed_at)
    head = _summarize(head_records)
    tail = _summarize(tail_records)
    age = age_seconds(windows["source"]["mtime_utc"], observed_at)
    issues = []
    if head["identity"]["sessionId"]["basis"] not in AGREED:
        issues.append("session_id_not_consistent_in_head")
    tail_session = tail["identity"]["sessionId"]["value"]
    if tail_session is not None and tail_session != head["identity"]["sessionId"]["value"]:
        issues.append("session_id_differs_between_head_and_tail")
    record.update({
        "source": windows["source"],
        "windows": {"head": {**public_window(windows["head"]), "parse": head_report},
                    "tail": {**public_window(windows["tail"]), "parse": tail_report}},
        "session_id": head["identity"]["sessionId"],
        "identity": head["identity"],
        "models_reported": sorted(set(head["models_reported"]) | set(tail["models_reported"])),
        "custom_title_ref": tail["custom_title_ref"] or head["custom_title_ref"],
        "first_timestamp_in_head": head["first_timestamp_in_window"],
        "last_timestamp_in_tail": tail["last_timestamp_in_window"],
        "tail": {k: tail[k] for k in ("record_type_counts", "content_block_counts",
                                      "tool_use_counts", "sidechain_records", "last_prompt_ref")},
        "last_user_prompt": _last_user_prompt(tail_records),
        "last_assistant": _last_assistant(tail_records),
        "file_age_seconds": age,
        "activity": activity_state(age),
        "issues": issues,
    })
    return record


__all__ = ["observe_claude_transcript"]
