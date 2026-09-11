"""Validation and private provenance helpers for provider-native tool turns."""
from __future__ import annotations

import json

from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError

_INCOMPLETE = {"incomplete", "cancelled", "failed", "expired"}


def reject_private_value(private_guard, value) -> None:
    if private_guard is None:
        return
    private_guard(value)


def provider_response_content(route, obj) -> dict:
    blocks = obj.get("output") if route == "openai_responses" else obj.get("content")
    key = "output" if route == "openai_responses" else "content"
    return {"schema": "flywheel.gateway-native-provider-observable-response/v1",
        "native_api_route": route, "id": obj.get("id"), "model": obj.get("model"),
        "status": obj.get("status"), "stop_reason": obj.get("stop_reason"),
        key: _observable_blocks(route, blocks)}


def provider_response_meta(route, binding, ordinal, obj) -> dict:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"schema": "flywheel.gateway-native-provider-response/v1",
        "binding_sha256": canonical_sha256(binding), "ordinal": ordinal,
        "endpoint": binding["endpoint"]["name"],
        "model_id": binding["model"]["model_id"],
        "native_api_route": route, "response_id": obj.get("id"),
        "response_sha256": canonical_sha256(obj),
        "response_bytes": len(raw.encode("utf-8")),
        "source_ids": _source_ids(route, obj),
        "continuity_items_opaque": _opaque_items(route, obj),
        "does_not_prove": ["MODEL_WEIGHTS_IDENTITY", "SEMANTIC_TRUTH"]}




def _observable_blocks(route, blocks):
    if not isinstance(blocks, list):
        return []
    return [(_observable_openai(item) if route == "openai_responses"
             else _observable_anthropic(item)) for item in blocks if isinstance(item, dict)]


def _observable_openai(item):
    value = {"type": item.get("type")}
    for key in ("id", "call_id", "name", "status"):
        if isinstance(item.get(key), str):
            value[key] = item[key]
    if item.get("type") == "function_call" and isinstance(item.get("arguments"), str):
        value["arguments"] = item["arguments"]
    if item.get("type") == "message" and isinstance(item.get("content"), list):
        value["content"] = [_observable_openai_block(block)
            for block in item["content"] if isinstance(block, dict)]
    if item.get("type") == "refusal" and isinstance(item.get("refusal"), str):
        value["refusal"] = item["refusal"]
    return value


def _observable_openai_block(block):
    value = {"type": block.get("type")}
    if block.get("type") in {"output_text", "text"} and isinstance(block.get("text"), str):
        value["text"] = block["text"]
    elif block.get("type") == "refusal" and isinstance(block.get("refusal"), str):
        value["refusal"] = block["refusal"]
    else:
        value["opaque"] = True
    return value


def _observable_anthropic(block):
    value = {"type": block.get("type")}
    for key in ("id", "name"):
        if isinstance(block.get(key), str):
            value[key] = block[key]
    if block.get("type") == "text" and isinstance(block.get("text"), str):
        value["text"] = block["text"]
    elif block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
        value["input"] = block["input"]
    elif block.get("type") == "refusal" and isinstance(block.get("refusal"), str):
        value["refusal"] = block["refusal"]
    elif block.get("type") not in {"text", "tool_use", "refusal"}:
        value["opaque"] = True
    return value


def _source_ids(route, obj):
    ids = []
    if isinstance(obj.get("id"), str):
        ids.append({"kind": "response", "id": obj["id"]})
    blocks = obj.get("output") if route == "openai_responses" else obj.get("content")
    if isinstance(blocks, list):
        for index, item in enumerate(blocks):
            if isinstance(item, dict):
                if isinstance(item.get("id"), str) and item["id"]:
                    ids.append({"kind": item.get("type"), "index": index, "id": item["id"]})
                if isinstance(item.get("call_id"), str) and item["call_id"]:
                    ids.append({"kind": "call", "index": index, "id": item["call_id"]})
    return ids


def _opaque_items(route, obj):
    blocks = obj.get("output") if route == "openai_responses" else obj.get("content")
    if not isinstance(blocks, list):
        return []
    items = []
    for index, item in enumerate(blocks):
        if isinstance(item, dict):
            items.append({"index": index, "type": item.get("type"),
                "id_present": isinstance(item.get("id"), str) and bool(item.get("id")),
                "call_id_present": isinstance(item.get("call_id"), str) and bool(item.get("call_id"))})
    return items


def openai_terminal_guard(obj) -> None:
    if obj.get("status") in _INCOMPLETE:
        raise GatewayOperationError("AGENT_NATIVE_INCOMPLETE")
    if obj.get("status") not in {None, "completed"}:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def anthropic_terminal_guard(obj) -> None:
    reason = obj.get("stop_reason")
    if reason in {"max_tokens", "pause_turn", "model_context_window_exceeded"}:
        raise GatewayOperationError("AGENT_NATIVE_INCOMPLETE")
    if reason in {"refusal", "safety"}:
        raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
    if reason not in {"tool_use", "end_turn"}:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def openai_calls(output, props, used):
    _validate_openai_output(output)
    calls, seen = [], set()
    for index, item in enumerate(output):
        if item.get("type") != "function_call":
            continue
        call_id, item_id = item.get("call_id"), item.get("id")
        call_key, item_key = "call:" + call_id, "item:" + item_id
        if (call_id == item_id or call_key in used or item_key in used
                or call_key in seen or item_key in seen):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        seen.update((call_key, item_key))
        args = _json_args(item.get("arguments"))
        _validate_args(item.get("name"), args, props)
        calls.append({"name": item["name"], "args": args,
            "provider_call_id": call_id, "provider_item_id": item_id,
            "provider_order_index": index})
    used.update(seen)
    return calls


def _validate_openai_output(output) -> None:
    for item in output:
        if not isinstance(item, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        status = item.get("status")
        if status is not None and status != "completed":
            if status in _INCOMPLETE:
                raise GatewayOperationError("AGENT_NATIVE_INCOMPLETE")
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        kind = item.get("type")
        if kind == "refusal":
            raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
        if kind == "function_call":
            if (type(item.get("call_id")) is not str or not item.get("call_id")
                    or type(item.get("id")) is not str or not item.get("id")):
                raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        if kind == "message":
            content = item.get("content")
            if not isinstance(content, list):
                raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
            for block in content:
                if not isinstance(block, dict):
                    raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
                if block.get("type") == "refusal":
                    raise GatewayOperationError("AGENT_NATIVE_REFUSAL")


def anthropic_calls(content, props, used):
    _validate_anthropic_content(content)
    calls, seen = [], set()
    for index, block in enumerate(content):
        if block.get("type") != "tool_use":
            continue
        call_id = block.get("id")
        call_key = "call:" + call_id
        if call_key in used or call_key in seen:
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        seen.add(call_key)
        args = block.get("input")
        if not isinstance(args, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        _validate_args(block.get("name"), args, props)
        calls.append({"name": block["name"], "args": args,
            "provider_call_id": call_id, "provider_item_id": call_id,
            "provider_order_index": index})
    used.update(seen)
    return calls


def _validate_anthropic_content(content) -> None:
    for block in content:
        if not isinstance(block, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        if block.get("type") == "refusal":
            raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
        if block.get("type") == "tool_use":
            if type(block.get("id")) is not str or not block.get("id"):
                raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def _validate_args(name, args, props) -> None:
    if type(name) is not str or name not in props or not isinstance(args, dict):
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    wanted = props[name]
    if set(args) != set(wanted):
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    for key, schema in wanted.items():
        kind = schema.get("type")
        if kind == "string" and type(args[key]) is not str:
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        if kind == "integer" and (type(args[key]) is not int or args[key] < schema.get("minimum", 0)):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def _json_args(raw):
    if type(raw) is not str:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR") from None
    if not isinstance(value, dict):
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    return value


def openai_text(output):
    pieces = []
    for item in output:
        if item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if block.get("type") in {"output_text", "text"} and isinstance(block.get("text"), str):
                pieces.append(block["text"])
    if not pieces:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    return "\n".join(pieces)


def anthropic_text(content):
    pieces = [block["text"] for block in content
              if block.get("type") == "text" and isinstance(block.get("text"), str)]
    if not pieces:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    return "\n".join(pieces)


def anthropic_tools(tools):
    return [{"name": t["name"], "description": t.get("description", ""),
             "input_schema": t["parameters"], "strict": True} for t in tools]
