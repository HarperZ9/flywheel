"""Split one transcript JSONL line into typed units.

Kinds: author (a person's typed message), assistant (model prose),
tool_call (tool name plus the command or path only), tool_result (outcome
only: ok or error), relay (task notifications, subagent briefs and
messages between agents). Everything else is noise and yields nothing:
attachments, hook context, system reminders, metadata records.

Large lines are mostly tool results and request blobs. They are classified
from a bounded head and tail slice, so a 10 MB tool output is never parsed.
"""

import json
import re

from harness.recall_index.gates import record_stopped

BIG_LINE = 256 * 1024
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
_TAGGED = re.compile(r"<(?:command-[a-z]+|local-command-[a-z]+)>.*?</[^>]+>", re.DOTALL)
_NOISE_PREFIX = ("<command-", "<local-command", "Caveat:", "[Request interrupted",
                 "<user-prompt-submit-hook>")
_RELAY_PREFIX = ("<task-notification>",)
_RELAY_TOOLS = {"Agent", "Task", "SendMessage"}
_SUMMARY_PREFIX = ("This session is being continued from a previous conversation",)
_NOTE_PARTS = re.compile(r"<(status|summary|result)>(.*?)</\1>", re.DOTALL)
_PATH_KEYS = ("file_path", "path", "notebook_path", "url", "pattern")
_TUID = re.compile(rb'"tool_use_id"\s*:\s*"([^"]+)"')
_ISERR = re.compile(rb'"is_error"\s*:\s*true')
_TYPE_UA = re.compile(rb'"type"\s*:\s*"(user|assistant)"')
_TOOL_RESULT = re.compile(rb'"type"\s*:\s*"tool_result"')


def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _clean(text: str) -> str:
    return _TAGGED.sub("", _REMINDER.sub("", text)).strip()


def _big_line_units(line: bytes) -> list[dict]:
    window = line[:4096] + line[-2048:]
    m_type = _TYPE_UA.search(window)
    if _TOOL_RESULT.search(line[:4096]) and m_type and m_type.group(1) == b"user":
        m = _TUID.search(line[:4096])
        err = bool(_ISERR.search(line[:4096]) or _ISERR.search(line[-2048:]))
        return [{"kind": "tool_result", "text": "", "meta": {
            "tuid": m.group(1).decode() if m else "", "error": err}}]
    if m_type and m_type.group(1) == b"assistant":
        return None  # parse it: big assistant lines carry tool inputs
    return []


def _user_units(rec: dict) -> list[dict]:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                out.append({"kind": "tool_result", "text": "", "meta": {
                    "tuid": b.get("tool_use_id", ""), "error": bool(b.get("is_error"))}})
        if out:
            return out
        content = " ".join(b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str) or rec.get("isMeta"):
        return []
    raw = content.lstrip()
    if raw.startswith(_RELAY_PREFIX):
        parts = " | ".join(v.strip() for _, v in _NOTE_PARTS.findall(raw)) or _clean(raw)
        return [{"kind": "relay", "text": _clip(parts, 1200), "meta": {}}]
    if raw.startswith(_SUMMARY_PREFIX):
        return [{"kind": "summary", "text": _clip(_clean(raw), 6000), "meta": {}}]
    if raw.startswith(_NOISE_PREFIX):
        return []
    text = _clean(raw)
    return [{"kind": "author", "text": _clip(text, 4000), "meta": {}}] if text else []


def _call_unit(block: dict) -> dict:
    name = block.get("name", "?")
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    meta = {"tool": name, "tuid": block.get("id", "")}
    if "command" in inp:
        meta["command"] = _clip(str(inp["command"]), 300)
        text = meta["command"]
    else:
        target = next((str(inp[k]) for k in _PATH_KEYS if k in inp), "")
        meta["target"] = _clip(target, 300)
        text = target
    if name in _RELAY_TOOLS:
        brief = str(inp.get("description") or "") + " " + str(inp.get("prompt") or
                                                                 inp.get("message") or "")
        return {"kind": "relay", "text": _clip(_clean(brief), 1200), "meta": meta}
    return {"kind": "tool_call", "text": f"{name} {text}".strip(), "meta": meta}


def _assistant_units(rec: dict) -> list[dict]:
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    out = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and b.get("text", "").strip():
            out.append({"kind": "assistant", "text": _clean(b["text"]), "meta": {}})
        elif b.get("type") == "tool_use":
            out.append(_call_unit(b))
    return out


def split_line(line: bytes) -> tuple[list[dict], dict]:
    """Units in one line, plus record facts: ts, uuid, sidechain, stopped."""
    facts = {"ts": "", "uuid": "", "stopped": False, "sidechain": False}
    if len(line) > 4096:
        if not _TYPE_UA.search(line[:600] + line[-600:]):
            return [], facts
    if len(line) > BIG_LINE:
        units = _big_line_units(line)
        if units is not None:
            return units, facts
    try:
        rec = json.loads(line)
    except ValueError:
        return [], facts
    if not isinstance(rec, dict):
        return [], facts
    facts.update(ts=str(rec.get("timestamp", "")), uuid=str(rec.get("uuid", "")),
                 sidechain=bool(rec.get("isSidechain")))
    kind = rec.get("type")
    if kind == "user":
        return _user_units(rec), facts
    if kind == "assistant":
        if record_stopped(rec):
            facts["stopped"] = True
            return [], facts
        return _assistant_units(rec), facts
    return [], facts
