"""gateway_responses_wire.py -- an OpenAI Responses request, read into a turn.

`parse` turns a `POST /v1/responses` body into a neutral `Turn` plus the
request fields the Response object echoes back. It refuses a malformed request,
and every feature outside the carried subset, with the field or item type named.

Carried: `input` as a string or as a list of items (`message` items with
`input_text` and `output_text` parts, in the short form and the typed form;
`function_call`; `function_call_output`), `instructions`, `tools` of type
`function`, `tool_choice`, `parallel_tool_calls`, `max_output_tokens`,
`temperature`, `top_p`, `stream`.

Refused: `previous_response_id` and `conversation` (the gateway stores no
responses), `background`, `prompt`, a `text.format` other than plain text,
built-in and custom tools, image, file and audio parts, `item_reference` and
every other item type.

Dropped: `reasoning` items in `input`. A reasoning item belongs to the provider
that made it and no upstream on this path can read another provider's. A
refusal would end a conversation that began on that provider, so the item is
left out and the conversation continues.

`system` and `developer` messages in `input` join `instructions` as system
text, in order. The flat item list becomes alternating turns: a
`function_call` joins the assistant turn before it, a `function_call_output`
joins the tool results after that turn.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      CreateResponse, EasyInputMessage, FunctionToolCall, FunctionToolCallOutput
  openai Python SDK 2.36.0, types/responses (generated from that spec):
      response_create_params, response_input_item_param,
      easy_input_message_param, function_tool_param, tool_choice_options,
      tool_choice_function_param
  https://developers.openai.com/api/docs/guides/function-calling
      the function tool, `function_call` and `function_call_output` shapes
"""
from __future__ import annotations

import json

from .gateway_turn import Turn, TurnRefused, check_results

INTERFACE = "openai-responses"
DEFAULT_MAX_TOKENS = 4096             # sent upstream when the client names no limit
_ROLES = ("user", "assistant", "system", "developer")
_TEXT_PARTS = ("input_text", "output_text")
_CHOICES = {"auto": "auto", "none": "none", "required": "any"}
# request field -> why the gateway cannot honour it
_REFUSED = {
    "previous_response_id": "the gateway stores no responses; send the whole "
                            "conversation in `input`",
    "conversation": "the gateway stores no conversations; send the whole "
                    "conversation in `input`",
    "background": "the gateway runs no background responses",
    "prompt": "the gateway holds no prompt templates",
    "context_management": "the gateway does not compact a conversation",
}


def refused(message: str, param: "str | None" = None) -> TurnRefused:
    """An invalid-request refusal that names the request field."""
    error = TurnRefused("invalid", message)
    error.param = param
    return error


def _parts_text(content, where: str, allowed=_TEXT_PARTS) -> str:
    """The text of a message's `content`, or of a function call's `output`."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise refused(f"{where}: must be a string or a list of content parts", where)
    texts = []
    for at, part in enumerate(content):
        kind = part.get("type") if isinstance(part, dict) else None
        if not isinstance(kind, str) or not kind:
            raise refused(f"{where}.{at}: a content part needs a type", f"{where}.{at}")
        if kind not in allowed:
            raise refused(f"{where}.{at}: content parts of type {kind!r} are not carried "
                          "by the gateway; only text parts are", f"{where}.{at}")
        if not isinstance(part.get("text"), str):
            raise refused(f"{where}.{at}.text: must be a string", f"{where}.{at}.text")
        texts.append(part["text"])
    return "\n".join(texts)


def _function_call(where: str, item: dict) -> dict:
    given, name, raw = item.get("call_id"), item.get("name"), item.get("arguments")
    if not (isinstance(given, str) and given and isinstance(name, str) and name
            and isinstance(raw, str)):
        raise refused(f"{where}: a function_call item needs call_id, name and a string "
                      "arguments", where)
    try:
        arguments = json.loads(raw or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        raise refused(f"{where}.arguments: must be a JSON object in a string",
                      f"{where}.arguments")
    return {"id": given, "name": name, "arguments": arguments}


def _last(rows: list, role: str) -> dict:
    """The neutral message this item joins: the last one of its role, or a new one."""
    if not rows or rows[-1]["role"] != role:
        rows.append({"role": role, "text": "", "calls": [], "results": []})
    return rows[-1]


def _add_text(rows: list, role: str, text: str) -> None:
    row = _last(rows, role)
    row["text"] = f"{row['text']}\n{text}" if row["text"] else text


def _add_output(rows: list, where: str, item: dict) -> None:
    given = item.get("call_id")
    if not (isinstance(given, str) and given):
        raise refused(f"{where}: a function_call_output item needs call_id", where)
    output = _parts_text(item.get("output"), f"{where}.output", ("input_text",))
    asked = rows[-1] if rows and rows[-1]["role"] == "assistant" else None
    if asked is None and len(rows) > 1 and rows[-1]["results"] and not rows[-1]["text"]:
        asked = rows[-2]                    # another output of the same turn came first
    if asked is None or given not in {call["id"] for call in asked["calls"]}:
        raise refused(
            f"{where}: function_call_output names a call_id that the function_call "
            "items before it did not produce; nothing was sent upstream",
            f"{where}.call_id")
    if rows[-1]["role"] == "assistant":
        rows.append({"role": "user", "text": "", "calls": [], "results": []})
    rows[-1]["results"].append({"id": given, "ok": True, "output": output})


def _items(raw) -> tuple:
    """(system texts, neutral messages) for the `input` field."""
    if isinstance(raw, str):
        return [], [{"role": "user", "text": raw, "calls": [], "results": []}]
    if not isinstance(raw, list) or not raw:
        raise refused("input: must be a string or a non-empty list of items", "input")
    system, rows = [], []
    for index, item in enumerate(raw):
        where = f"input.{index}"
        if not isinstance(item, dict):
            raise refused(f"{where}: an input item must be an object", where)
        kind = item.get("type") or ("message" if "role" in item else None)
        if kind == "message":
            role = item.get("role")
            if role not in _ROLES:
                raise refused(f"{where}.role: must be user, assistant, system or "
                              "developer", f"{where}.role")
            text = _parts_text(item.get("content"), f"{where}.content")
            if role in ("system", "developer"):
                system.append(text)
            else:
                _add_text(rows, role, text)
        elif kind == "function_call":
            _last(rows, "assistant")["calls"].append(_function_call(where, item))
        elif kind == "function_call_output":
            _add_output(rows, where, item)
        elif kind != "reasoning":           # reasoning items are dropped, see above
            raise refused(f"{where}: input items of type {kind!r} are not carried by "
                          "the gateway", where)
    if not rows:
        raise refused("input: needs at least one user or assistant item", "input")
    return system, rows


def _tools(raw) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise refused("tools: must be a list", "tools")
    specs = []
    for index, tool in enumerate(raw):
        where = f"tools.{index}"
        if not isinstance(tool, dict):
            raise refused(f"{where}: must be an object", where)
        if tool.get("type") != "function":
            raise refused(f"{where}: tools of type {tool.get('type')!r} are not carried "
                          "by the gateway; only `function` tools are", where)
        name, schema = tool.get("name"), tool.get("parameters")
        if not (isinstance(name, str) and name) or not isinstance(schema, (dict, type(None))):
            raise refused(f"{where}: a function tool needs name and an object parameters",
                          where)
        specs.append({"name": name, "description": str(tool.get("description") or ""),
                      "parameters": schema or {"type": "object", "properties": {}}})
    return specs


def _tool_choice(body: dict) -> "dict | None":
    raw, parallel = body.get("tool_choice"), body.get("parallel_tool_calls") is not False
    if raw is None:
        return None if parallel else {"mode": "auto", "name": "", "parallel": False}
    if isinstance(raw, str) and raw in _CHOICES:
        return {"mode": _CHOICES[raw], "name": "", "parallel": parallel}
    if isinstance(raw, dict) and raw.get("type") == "function":
        if not (isinstance(raw.get("name"), str) and raw["name"]):
            raise refused("tool_choice.name: required when type is function",
                          "tool_choice.name")
        return {"mode": "tool", "name": raw["name"], "parallel": parallel}
    raise refused("tool_choice: must be auto, none, required or "
                  '{"type": "function", "name": ...}', "tool_choice")


def _number(body: dict, key: str) -> "float | None":
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise refused(f"{key}: must be a number", key)
    return float(value)


def _limit(body: dict) -> int:
    limit = body.get("max_output_tokens")
    if limit is None:
        return DEFAULT_MAX_TOKENS
    if type(limit) is not int or limit < 1:
        raise refused("max_output_tokens: must be a positive integer", "max_output_tokens")
    return limit


def _unsupported(body: dict) -> None:
    for key, why in _REFUSED.items():
        if body.get(key) not in (None, False):
            raise refused(f"{key}: not supported; {why}", key)
    text = body.get("text")
    if text is not None:
        form = text.get("format") if isinstance(text, dict) else 0
        kind = "text" if form is None else form.get("type") if isinstance(form, dict) else None
        if kind != "text":
            raise refused("text.format: only plain text output is carried by the "
                          "gateway", "text.format")


def parse(body) -> tuple:
    """(Turn, echo) for a Responses request body, or TurnRefused("invalid").

    `echo` holds the request fields a Response object repeats.
    """
    if not isinstance(body, dict):
        raise refused("request body must be a JSON object")
    model, instructions = body.get("model"), body.get("instructions")
    if not isinstance(model, str) or not model.strip():
        raise refused("model: field required", "model")
    if instructions is not None and not isinstance(instructions, str):
        raise refused("instructions: must be a string", "instructions")
    _unsupported(body)
    system, rows = _items(body.get("input"))
    turn = Turn(
        interface=INTERFACE, model=model,
        system="\n".join(([instructions] if instructions else []) + system),
        messages=rows, tools=_tools(body.get("tools")), tool_choice=_tool_choice(body),
        max_tokens=_limit(body), temperature=_number(body, "temperature"),
        top_p=_number(body, "top_p"), stream=body.get("stream") is True)
    check_results(turn.messages)
    echo = {"instructions": instructions, "max_output_tokens": body.get("max_output_tokens"),
            "parallel_tool_calls": body.get("parallel_tool_calls") is not False,
            "temperature": turn.temperature, "top_p": turn.top_p,
            "tool_choice": body.get("tool_choice") or "auto",
            "tools": body.get("tools") or [],
            "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {}}
    return turn, echo
