"""endpoints_tools_wire.py -- each provider's function-calling shapes.

`outgoing` turns a request the text protocol would send into the provider's
native form: tool schemas added, and each earlier turn that came back
natively sent again as the provider's own tool-call and tool-result objects.
`incoming` reads a reply's native tool calls and hands them to
endpoints_tools.absorb, which writes them as TOOL lines.

An earlier native turn is replayed exactly as the provider sent it. That
keeps whatever the provider attached to its own calls (an Anthropic thinking
block, a Gemini thoughtSignature) without this module having to know it.

Wire formats, read 2026-11-13:
  Anthropic  https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
             (tool_use and tool_result blocks; results first in the user turn)
  OpenAI     https://github.com/openai/openai-openapi (manual_spec branch):
             ChatCompletionTool, FunctionObject, ChatCompletionMessageToolCall,
             ChatCompletionRequestToolMessage
  Gemini     https://aistudio.google.com/api-reference/generate-content
             (Tool, FunctionDeclaration.parametersJsonSchema, FunctionCall,
             FunctionResponse, Part.thoughtSignature)
"""
from __future__ import annotations

from . import endpoints_cache as _cache, endpoints_tools as _tools


def _noted(system: str) -> str:
    """The system prompt for a native request: call through the interface, not as text."""
    from .local_tools import TOOLS_SYSTEM
    system = system.replace(TOOLS_SYSTEM, _tools.GUIDE)
    return f"{system}\n\n{_tools.NOTE}" if system else _tools.NOTE


def _turns(found: dict, messages: list, plain, native_pair) -> list:
    """The conversation, with each matched (assistant, results) pair made native."""
    wire, skip = [], -1
    for index, message in enumerate(messages):
        if index == skip:
            continue
        if index in found:
            reply, results = found[index]
            wire += native_pair(reply, results)
            skip = index + 1
        else:
            wire.append(plain(message))
    return wire


def _openai_pair(reply, results) -> list:
    return [reply.raw] + [
        {"role": "tool", "tool_call_id": call["id"],
         "content": ("ok:\n" if ok else "FAIL:\n") + output}
        for call, (ok, output) in zip(reply.calls, results)]


def _anthropic_pair(reply, results) -> list:
    blocks = [{"type": "tool_result", "tool_use_id": call["id"], "content": output,
               **({"is_error": True} if not ok else {})}
              for call, (ok, output) in zip(reply.calls, results)]
    return [{"role": "assistant", "content": reply.raw}, {"role": "user", "content": blocks}]


def _gemini_pair(reply, results) -> list:
    parts = []
    for call, (ok, output) in zip(reply.calls, results):
        answer = {"name": call["name"], "response": {"output" if ok else "error": output}}
        if call.get("id"):
            answer["id"] = call["id"]
        parts.append({"functionResponse": answer})
    return [{"role": "model", "parts": reply.raw}, {"role": "user", "parts": parts}]


def _openai_out(found, specs, messages, system, payload) -> dict:
    wire = [{"role": "system", "content": _noted(system)}]
    wire += _turns(found, messages, lambda m: m, _openai_pair)
    tools = [{"type": "function", "function": dict(spec)} for spec in specs]
    return {**payload, "messages": wire, "tools": tools}


def _anthropic_out(found, specs, messages, system, payload) -> dict:
    wire = _turns(found, messages, lambda m: {"role": m["role"], "content": m["content"]},
                  _anthropic_pair)
    tools = [{"name": s["name"], "description": s["description"],
              "input_schema": s["parameters"]} for s in specs]
    return {**payload, "messages": wire, "system": _noted(system), "tools": tools}


def _gemini_out(found, specs, messages, system, payload) -> dict:
    def plain(m):
        return {"role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}]}
    declarations = [{"name": s["name"], "description": s["description"],
                     "parametersJsonSchema": s["parameters"]} for s in specs]
    return {**payload, "contents": _turns(found, messages, plain, _gemini_pair),
            "systemInstruction": {"parts": [{"text": _noted(system)}]},
            "tools": [{"functionDeclarations": declarations}]}


_OUT = {"openai": _openai_out, "anthropic": _anthropic_out, "gemini": _gemini_out}


def outgoing(dialect: str, backend, messages: list, system: str, payload: dict) -> dict:
    """The request body to send: native and cache-marked when a session asks for it."""
    offer = _tools.offered(backend)
    if offer is not None:
        box, specs = offer
        found = _tools.matched(box, dialect, list(messages))
        payload = _OUT[dialect](found, specs, list(messages), system, payload)
    return _cache.marked(dialect, backend, payload)


def refused(backend, status: int, obj, payload: dict) -> bool:
    """True when the host turned down something a session added; ask again without it."""
    return (_tools.refused(backend, status, obj, payload)
            or _cache.refused(backend, status, obj, payload))


def _openai_in(obj, gen) -> tuple:
    message = obj["choices"][0]["message"]
    calls = gen.get("tool_calls") or []
    claimed = message.get("role") == "tool" or "tool_call_id" in message
    raw = {"role": "assistant", "content": message.get("content"),
           "tool_calls": message.get("tool_calls")}
    return calls, raw, claimed, True


def _anthropic_in(obj, gen) -> tuple:
    blocks = obj["content"]
    calls = [{"id": b.get("id"), "name": b.get("name"), "arguments": b.get("input")}
             for b in blocks if b.get("type") == "tool_use"]
    claimed = any(str(b.get("type", "")).endswith("tool_result") for b in blocks)
    return calls, blocks, claimed, True


def _gemini_in(obj, gen) -> tuple:
    parts = obj["candidates"][0]["content"]["parts"]
    calls = [{"id": p["functionCall"].get("id"), "name": p["functionCall"].get("name"),
              "arguments": p["functionCall"].get("args") or {}}
             for p in parts if isinstance(p.get("functionCall"), dict)]
    claimed = any("functionResponse" in p or "codeExecutionResult" in p for p in parts)
    return calls, parts, claimed, False


_IN = {"openai": _openai_in, "anthropic": _anthropic_in, "gemini": _gemini_in}


def incoming(dialect: str, backend, obj, gen: dict) -> dict:
    """`gen` with its text in text-protocol form when the reply held native calls."""
    if _tools.current() is None:
        return gen
    calls, raw, claimed, needs_id = _IN[dialect](obj, gen)
    if needs_id and not all(isinstance(c.get("id"), str) and c["id"] for c in calls):
        raw = None                       # cannot be answered natively; travels as text
    gen["text"] = _tools.absorb(dialect, backend, gen["text"], calls, raw, claimed)
    return gen
