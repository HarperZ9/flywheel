"""gateway_turn_wire.py -- a neutral turn, written in each upstream's own shape.

`request` returns (url, headers, payload) for one turn and one upstream. The
url and headers are the ones the upstream's backend builds for any call, so
the credential travels the way it always has. The payload carries the
conversation with native tool schemas, tool calls and tool results. Tool names
and the system prompt reach the upstream unchanged.

What has no equivalent is left out and listed in docs/GATEWAY-INTERFACES.md:
`is_error` on an OpenAI tool message, and a forced tool choice on Gemini.

Wire formats, read 2026-11-13:
  Anthropic  https://platform.claude.com/docs/en/api/messages/create
             https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
  OpenAI     https://github.com/openai/openai-openapi (manual_spec branch):
             ChatCompletionTool, ChatCompletionMessageToolCall,
             ChatCompletionRequestToolMessage; tool_choice values and
             parallel_tool_calls as typed in the openai Python SDK 2.36.0
  Gemini     https://aistudio.google.com/api-reference/generate-content
             (Tool, FunctionDeclaration.parametersJsonSchema, FunctionCall,
             FunctionResponse)
"""
from __future__ import annotations

import json


def _user_row(message: dict) -> bool:
    """Does this user turn carry a text row of its own?"""
    return bool(message["text"]) or not message.get("results")


def _openai_messages(turn) -> list:
    rows = [{"role": "system", "content": turn.system}] if turn.system else []
    for message in turn.messages:
        for result in message.get("results") or []:
            rows.append({"role": "tool", "tool_call_id": result["id"],
                         "content": result["output"]})
        if message["role"] == "assistant":
            row = {"role": "assistant", "content": message["text"] or None}
            if message.get("calls"):
                row["tool_calls"] = [
                    {"id": call["id"], "type": "function", "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"], ensure_ascii=False)}}
                    for call in message["calls"]]
            rows.append(row)
        elif _user_row(message):
            rows.append({"role": "user", "content": message["text"]})
    return rows


def _openai(turn, backend) -> dict:
    payload = {"model": backend.model, "messages": _openai_messages(turn),
               "max_tokens": turn.max_tokens}
    for key, value in (("temperature", turn.temperature), ("top_p", turn.top_p),
                       ("stop", turn.stop or None)):
        if value is not None:
            payload[key] = value
    if turn.tools:
        payload["tools"] = [{"type": "function", "function": dict(spec)}
                            for spec in turn.tools]
        choice = turn.tool_choice or {}
        mode = choice.get("mode")
        if mode == "tool":
            payload["tool_choice"] = {"type": "function",
                                      "function": {"name": choice.get("name", "")}}
        elif mode in ("auto", "any", "none"):
            payload["tool_choice"] = {"any": "required"}.get(mode, mode)
        if choice.get("parallel") is False:
            payload["parallel_tool_calls"] = False
    return payload


def _anthropic_messages(turn) -> list:
    rows = []
    for message in turn.messages:
        if message["role"] == "assistant":
            blocks = [{"type": "text", "text": message["text"]}] if message["text"] else []
            blocks += [{"type": "tool_use", "id": call["id"], "name": call["name"],
                        "input": call["arguments"]} for call in message.get("calls") or []]
            rows.append({"role": "assistant", "content": blocks})
            continue
        blocks = [{"type": "tool_result", "tool_use_id": result["id"],
                   "content": result["output"],
                   **({} if result["ok"] else {"is_error": True})}
                  for result in message.get("results") or []]
        if not blocks:
            rows.append({"role": "user", "content": message["text"]})
            continue
        if message["text"]:                 # results first, then text
            blocks.append({"type": "text", "text": message["text"]})
        rows.append({"role": "user", "content": blocks})
    return rows


def _anthropic(turn, backend) -> dict:
    payload = {"model": backend.model, "max_tokens": turn.max_tokens,
               "messages": _anthropic_messages(turn)}
    for key, value in (("system", turn.system or None), ("temperature", turn.temperature),
                       ("top_p", turn.top_p), ("stop_sequences", turn.stop or None)):
        if value is not None:
            payload[key] = value
    if turn.tools:
        payload["tools"] = [{"name": spec["name"], "description": spec["description"],
                             "input_schema": spec["parameters"]} for spec in turn.tools]
        choice = turn.tool_choice or {}
        if choice.get("mode"):
            sent = {"type": choice["mode"]}
            if choice["mode"] == "tool":
                sent["name"] = choice.get("name", "")
            if choice.get("parallel") is False and choice["mode"] != "none":
                sent["disable_parallel_tool_use"] = True
            payload["tool_choice"] = sent
    return payload


def _gemini_contents(turn) -> list:
    names, rows = {}, []                    # call id -> tool name, for the result parts
    for message in turn.messages:
        if message["role"] == "assistant":
            parts = [{"text": message["text"]}] if message["text"] else []
            for call in message.get("calls") or []:
                names[call["id"]] = call["name"]
                parts.append({"functionCall": {"name": call["name"],
                                               "args": call["arguments"]}})
            rows.append({"role": "model", "parts": parts})
            continue
        parts = [{"functionResponse": {
            "name": names.get(result["id"], ""),
            "response": {"output" if result["ok"] else "error": result["output"]}}}
            for result in message.get("results") or []]
        if _user_row(message):
            parts.append({"text": message["text"]})
        rows.append({"role": "user", "parts": parts})
    return rows


def _gemini(turn, backend) -> dict:
    config = {"maxOutputTokens": turn.max_tokens}
    for key, value in (("temperature", turn.temperature), ("topP", turn.top_p),
                       ("stopSequences", turn.stop or None)):
        if value is not None:
            config[key] = value
    payload = {"contents": _gemini_contents(turn), "generationConfig": config}
    if turn.system:
        payload["systemInstruction"] = {"parts": [{"text": turn.system}]}
    # "none" is carried by leaving the tools out; a forced choice is not carried.
    if turn.tools and (turn.tool_choice or {}).get("mode") != "none":
        payload["tools"] = [{"functionDeclarations": [
            {"name": spec["name"], "description": spec["description"],
             "parametersJsonSchema": spec["parameters"]} for spec in turn.tools]}]
    return payload


_WRITE = {"openai": _openai, "anthropic": _anthropic, "gemini": _gemini}


def endpoint(upstream, max_tokens: int = 1) -> tuple:
    """(url, headers) the upstream's backend uses for a call."""
    url, headers, _payload = upstream.backend._request([], "", max_tokens, 0.0)
    return url, headers


def request(turn, upstream) -> tuple:
    """(url, headers, payload) for this turn on this upstream."""
    url, headers = endpoint(upstream, turn.max_tokens)
    return url, headers, _WRITE[upstream.dialect](turn, upstream.backend)
