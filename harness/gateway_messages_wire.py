"""gateway_messages_wire.py -- the Anthropic Messages format, read and written.

`parse` turns a Messages request body into a neutral `Turn` and refuses a
malformed one with the reason. `message` writes a `Reply` as a Message object,
`sse` writes one stream event, and `error` writes the error body.

Content only an Anthropic upstream can carry (image and document blocks,
server tools) is noted on the turn as `uncarried` and not refused here: the
handler forwards it untouched to an Anthropic upstream and refuses it, naming
the block type, for any other. Thinking blocks in history are left out of the
neutral turn; an Anthropic upstream still receives them in the forwarded body.

Wire format, read 2026-11-13:
  https://platform.claude.com/docs/en/api/messages/create
      request fields, content block types, the Message object, stop_reason
      values, usage fields (cache_creation_input_tokens and
      cache_read_input_tokens are numbers or null)
  https://platform.claude.com/docs/en/build-with-claude/streaming
      event order and delta types
  https://platform.claude.com/docs/en/api/errors
      the error body and the status to error type table
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
      tool_use and tool_result blocks; results come first in the user turn
"""
from __future__ import annotations

import json

from .gateway_turn import Turn, TurnRefused, check_results

INTERFACE = "anthropic-messages"
_DROPPED = ("thinking", "redacted_thinking")
_MODES = ("auto", "any", "tool", "none")
_STOP = {"end": "end_turn", "length": "max_tokens", "tool": "tool_use", "refusal": "refusal"}
_TYPES = {400: "invalid_request_error", 401: "authentication_error", 403: "permission_error",
          404: "not_found_error", 413: "request_too_large", 429: "rate_limit_error",
          500: "api_error", 504: "timeout_error", 529: "overloaded_error"}


def _bad(message: str) -> TurnRefused:
    return TurnRefused("invalid", message)


def _text_of(content, where: str, uncarried: list) -> str:
    """The text of a `system` value or a tool result's content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise _bad(f"{where}: must be a string or a list of content blocks")
    parts = []
    for block in content:
        if not isinstance(block, dict):
            raise _bad(f"{where}: a content block must be an object")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        else:
            uncarried.append(str(block.get("type")))
    return "\n".join(parts)


def _tool_use(where: str, block: dict) -> dict:
    given, name, arguments = block.get("id"), block.get("name"), block.get("input")
    if not (isinstance(given, str) and given and isinstance(name, str) and name
            and isinstance(arguments, dict)):
        raise _bad(f"{where}: a tool_use block needs id, name and an object input")
    return {"id": given, "name": name, "arguments": arguments}


def _tool_result(where: str, block: dict, uncarried: list) -> dict:
    given = block.get("tool_use_id")
    if not (isinstance(given, str) and given):
        raise _bad(f"{where}: a tool_result block needs tool_use_id")
    return {"id": given, "ok": block.get("is_error") is not True,
            "output": _text_of(block.get("content"), where + ".content", uncarried)}


def _message(index: int, raw, uncarried: list) -> dict:
    if not isinstance(raw, dict) or raw.get("role") not in ("user", "assistant"):
        raise _bad(f"messages.{index}.role: must be 'user' or 'assistant'")
    role, content = raw["role"], raw.get("content")
    out = {"role": role, "text": "", "calls": [], "results": []}
    if isinstance(content, str):
        out["text"] = content
        return out
    if not isinstance(content, list):
        raise _bad(f"messages.{index}.content: must be a string or a list of content blocks")
    texts = []
    for at, block in enumerate(content):
        where = f"messages.{index}.content.{at}"
        kind = block.get("type") if isinstance(block, dict) else None
        if not isinstance(kind, str) or not kind:
            raise _bad(f"{where}: a content block needs a type")
        if kind == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif kind == "tool_use" and role == "assistant":
            out["calls"].append(_tool_use(where, block))
        elif kind == "tool_result" and role == "user":
            out["results"].append(_tool_result(where, block, uncarried))
        elif not (kind in _DROPPED and role == "assistant"):
            uncarried.append(kind)
    out["text"] = "\n".join(texts)
    return out


def _tools(raw, uncarried: list) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _bad("tools: must be a list")
    specs = []
    for index, tool in enumerate(raw):
        if not isinstance(tool, dict):
            raise _bad(f"tools.{index}: must be an object")
        if tool.get("type") not in (None, "custom"):
            uncarried.append(f"{tool.get('type')} tool")     # a server tool
            continue
        name, schema = tool.get("name"), tool.get("input_schema")
        if not (isinstance(name, str) and name and isinstance(schema, dict)):
            raise _bad(f"tools.{index}: needs name and an object input_schema")
        specs.append({"name": name, "description": str(tool.get("description") or ""),
                      "parameters": schema})
    return specs


def _tool_choice(raw) -> "dict | None":
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("type") not in _MODES:
        raise _bad("tool_choice.type: must be auto, any, tool or none")
    if raw["type"] == "tool" and not (isinstance(raw.get("name"), str) and raw["name"]):
        raise _bad("tool_choice.name: required when type is tool")
    return {"mode": raw["type"], "name": raw.get("name") or "",
            "parallel": raw.get("disable_parallel_tool_use") is not True}


def _number(body: dict, key: str) -> "float | None":
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(f"{key}: must be a number")
    return float(value)


def _stops(raw) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise _bad("stop_sequences: must be a list of strings")
    return list(raw)


def parse(body) -> Turn:
    """A Messages request body as a neutral `Turn`, or TurnRefused("invalid")."""
    if not isinstance(body, dict):
        raise _bad("request body must be a JSON object")
    model, limit, rows = body.get("model"), body.get("max_tokens"), body.get("messages")
    if not isinstance(model, str) or not model.strip():
        raise _bad("model: field required")
    if limit is None:
        raise _bad("max_tokens: field required")
    if type(limit) is not int or limit < 1:
        raise _bad("max_tokens: must be a positive integer")
    if not isinstance(rows, list) or not rows:
        raise _bad("messages: must be a non-empty list")
    uncarried: list = []
    turn = Turn(
        interface=INTERFACE, model=model,
        system=_text_of(body.get("system"), "system", uncarried),
        messages=[_message(index, raw, uncarried) for index, raw in enumerate(rows)],
        tools=_tools(body.get("tools"), uncarried),
        tool_choice=_tool_choice(body.get("tool_choice")), max_tokens=limit,
        temperature=_number(body, "temperature"), top_p=_number(body, "top_p"),
        stop=_stops(body.get("stop_sequences")), stream=body.get("stream") is True,
        uncarried=uncarried)
    check_results(turn.messages)
    return turn


def usage(reply) -> dict:
    """The provider's counts under the Messages names. A missing count is 0 for
    input and output (with x_flywheel.usage_reported false) and null for cache."""
    counts = reply.usage
    return {"input_tokens": counts.get("input") or 0,
            "output_tokens": counts.get("output") or 0,
            "cache_creation_input_tokens": counts.get("cache_write"),
            "cache_read_input_tokens": counts.get("cache_read")}


def flags(reply) -> dict:
    """`x_flywheel.usage_reported`, on every reply: false marks counts that are
    0 because the provider sent none. The `anthropic` SDK (0.95.0,
    types/usage.py) types input_tokens and output_tokens as required integers,
    so null is not sent here."""
    return {"x_flywheel": {"usage_reported": reply.usage_reported}}


def content(reply) -> list:
    blocks = [{"type": "text", "text": reply.text}] if reply.text else []
    return blocks + [{"type": "tool_use", "id": call["id"], "name": call["name"],
                      "input": call["arguments"]} for call in reply.calls]


def message(reply, model: str, message_id: str, receipt: dict) -> dict:
    """A `Reply` as a Message object, with the receipt as an extension field."""
    return {"id": message_id, "type": "message", "role": "assistant", "model": model,
            "content": content(reply), "stop_reason": _STOP[reply.stop_reason],
            "stop_sequence": None, "usage": usage(reply), **flags(reply),
            "x_receipt": receipt}


def stop_reason(reply) -> str:
    return _STOP[reply.stop_reason]


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


def error(status: int, text: str, request_id: str = "") -> dict:
    return {"type": "error", "error": {"type": _TYPES.get(status, "api_error"),
                                       "message": text}, "request_id": request_id}
