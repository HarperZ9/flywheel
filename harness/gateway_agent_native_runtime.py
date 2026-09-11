"""Provider-native turn loops for bound supervised agent runs."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import time
from copy import deepcopy

from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .local_loop import _edit_fingerprint, _result_meta
from .proposer import normalize_usage


def run_native_protocol_loop(route, goal, binding, key, transport, executor,
                             ledger, sign_key, deadline, on_event, tools, props):
    if route == "openai_responses":
        return _openai_loop(goal, binding, key, transport, executor, ledger,
                            sign_key, deadline, on_event, tools, props)
    if route == "anthropic_messages":
        return _anthropic_loop(goal, binding, key, transport, executor, ledger,
                               sign_key, deadline, on_event, tools, props)
    raise GatewayOperationError("AGENT_BINDING_DRIFT")


def execute_native_test_command(test_cmd, executor, ledger, sign_key,
                                on_event, deadline):
    return _execute({"name": "run", "args": {"cmd": test_cmd},
        "provider_call_id": "test_cmd", "provider_item_id": "test_cmd",
        "provider_order_index": 0}, executor, ledger, sign_key,
        {"native_block": False, "gate": "test"}, on_event, deadline)

def _openai_loop(goal, binding, key, transport, executor, ledger, sign_key,
                 deadline, on_event, tools, props):
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    url = binding["endpoint"]["base_url"] + "/responses"
    input_items, used = [{"role": "user", "content": goal}], set()
    for step in range(1, binding["budget"]["max_steps"] + 1):
        payload = {"model": binding["model"]["model_id"], "input": input_items,
            "max_output_tokens": binding["budget"]["max_tokens"], "store": False,
            "parallel_tool_calls": False, "tools": tools, "stream": False,
            "temperature": 0}
        obj = _call(binding, transport, url, payload, headers, ledger, step, deadline)
        _openai_terminal_guard(obj)
        output = obj.get("output")
        if not isinstance(output, list):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        calls = _openai_calls(output, props, used)
        if not calls:
            text = _openai_text(output)
            ledger.append("assistant", text, {"backend": binding["endpoint"]["name"],
                "native_api_route": "openai_responses", "response_id": obj.get("id")})
            return text, step
        results = []
        for call in calls:
            res = _execute(call, executor, ledger, sign_key, _call_meta(
                "openai_responses", obj, call), on_event, deadline)
            results.append({"type": "function_call_output",
                "call_id": call["provider_call_id"], "output": res.output})
        input_items = deepcopy(output) + results
    return "[max_steps reached without a final answer]", binding["budget"]["max_steps"]


def _anthropic_loop(goal, binding, key, transport, executor, ledger, sign_key,
                    deadline, on_event, tools, props):
    headers = {"Content-Type": "application/json", "x-api-key": key,
               "anthropic-version": "2023-06-01"}
    url = binding["endpoint"]["base_url"] + "/v1/messages"
    messages, used = [{"role": "user", "content": goal}], set()
    for step in range(1, binding["budget"]["max_steps"] + 1):
        payload = {"model": binding["model"]["model_id"], "messages": messages,
            "max_tokens": binding["budget"]["max_tokens"],
            "tools": _anthropic_tools(tools), "stream": False}
        obj = _call(binding, transport, url, payload, headers, ledger, step, deadline)
        _anthropic_terminal_guard(obj)
        content = obj.get("content")
        if not isinstance(content, list):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        calls = _anthropic_calls(content, props, used)
        if not calls:
            text = _anthropic_text(content)
            ledger.append("assistant", text, {"backend": binding["endpoint"]["name"],
                "native_api_route": "anthropic_messages", "response_id": obj.get("id")})
            return text, step
        messages.append({"role": "assistant", "content": deepcopy(content)})
        blocks = []
        for call in calls:
            res = _execute(call, executor, ledger, sign_key, _call_meta(
                "anthropic_messages", obj, call), on_event, deadline)
            blocks.append({"type": "tool_result", "tool_use_id": call["provider_call_id"],
                           "content": res.output})
        messages.append({"role": "user", "content": blocks})
    return "[max_steps reached without a final answer]", binding["budget"]["max_steps"]


def _call(binding, transport, url, payload, headers, ledger, ordinal, deadline):
    if time.monotonic() >= deadline:
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    started = time.monotonic()
    _inference(ledger, binding, ordinal, "started", None, None)
    try:
        status, obj = transport("POST", url, headers,
            json.dumps(payload, separators=(",", ":")).encode(), binding["budget"]["timeout_s"])
        elapsed = int(max(0, (time.monotonic() - started) * 1000))
        if not 200 <= status < 300:
            ledger.append("provider_error", "", {"status": status, "response": obj})
            _inference(ledger, binding, ordinal, "failed", elapsed, "EXTERNAL_ACTION_FAILED")
            raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
        _inference(ledger, binding, ordinal, "response_received", elapsed, None)
        _model_call(ledger, binding, ordinal, obj, elapsed)
        return obj
    except GatewayOperationError:
        raise
    except Exception:
        _inference(ledger, binding, ordinal, "failed",
                   int(max(0, (time.monotonic() - started) * 1000)),
                   "EXTERNAL_ACTION_FAILED")
        raise


def _openai_calls(output, props, used):
    calls, seen = [], set()
    for index, item in enumerate(output):
        if not isinstance(item, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        if item.get("type") != "function_call":
            continue
        call_id, item_id = item.get("call_id"), item.get("id")
        if (type(call_id) is not str or not call_id or type(item_id) is not str
                or call_id == item_id or call_id in used or call_id in seen):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        seen.add(call_id)
        args = _json_args(item.get("arguments"))
        _validate_args(item.get("name"), args, props)
        calls.append({"name": item["name"], "args": args,
            "provider_call_id": call_id, "provider_item_id": item_id,
            "provider_order_index": index})
    used.update(seen)
    return calls


def _anthropic_calls(content, props, used):
    calls, seen = [], set()
    for index, block in enumerate(content):
        if not isinstance(block, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        if block.get("type") != "tool_use":
            continue
        call_id = block.get("id")
        if (type(call_id) is not str or not call_id or call_id in used
                or call_id in seen):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        seen.add(call_id)
        args = block.get("input")
        if not isinstance(args, dict):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        _validate_args(block.get("name"), args, props)
        calls.append({"name": block["name"], "args": args,
            "provider_call_id": call_id, "provider_item_id": call_id,
            "provider_order_index": index})
    used.update(seen)
    return calls


def _validate_args(name, args, props):
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


def _openai_text(output):
    pieces = []
    for item in output:
        if item.get("type") == "refusal":
            raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
        if item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if not isinstance(block, dict):
                raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
            if block.get("type") == "refusal":
                raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
            if block.get("type") in {"output_text", "text"} and isinstance(block.get("text"), str):
                pieces.append(block["text"])
    if not pieces:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    return "\n".join(pieces)


def _anthropic_text(content):
    pieces = []
    for block in content:
        if block.get("type") == "refusal":
            raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            pieces.append(block["text"])
    if not pieces:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
    return "\n".join(pieces)


def _openai_terminal_guard(obj):
    if obj.get("status") in {"incomplete", "cancelled", "failed", "expired"}:
        raise GatewayOperationError("AGENT_NATIVE_INCOMPLETE")
    if obj.get("status") not in {None, "completed"}:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def _anthropic_terminal_guard(obj):
    reason = obj.get("stop_reason")
    if reason in {"max_tokens", "pause_turn", "model_context_window_exceeded"}:
        raise GatewayOperationError("AGENT_NATIVE_INCOMPLETE")
    if reason in {"refusal", "safety"}:
        raise GatewayOperationError("AGENT_NATIVE_REFUSAL")
    if reason not in {"tool_use", "end_turn"}:
        raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")


def _anthropic_tools(tools):
    return [{"name": t["name"], "description": t.get("description", ""),
             "input_schema": t["parameters"]} for t in tools]


def _call_meta(route, obj, call):
    return {"schema": "flywheel.gateway-native-tool-call/v1", "native_block": True,
        "native_api_route": route, "provider_response_id": obj.get("id"),
        "provider_call_id": call["provider_call_id"],
        "provider_item_id": call["provider_item_id"],
        "provider_order_index": call["provider_order_index"],
        "result_order_policy": "provider_order_sequential"}


def _inference(ledger, binding, ordinal, phase, elapsed_ms, reason):
    ledger.append("model_inference", "", {"schema": "flywheel.gateway-agent-inference/v1",
        "binding_sha256": canonical_sha256(binding), "ordinal": ordinal,
        "endpoint": binding["endpoint"]["name"], "model_id": binding["model"]["model_id"],
        "phase": phase, "observed_at_utc": datetime.now(UTC).isoformat(),
        "elapsed_ms": elapsed_ms, "reason": reason})


def _model_call(ledger, binding, ordinal, obj, elapsed_ms):
    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else None
    ledger.append("model_call", "", {"schema": "flywheel.gateway-agent-model-call/v1",
        "binding_sha256": canonical_sha256(binding), "ordinal": ordinal,
        "endpoint": binding["endpoint"]["name"], "requested_model_reference":
        binding["model"]["requested_model_reference"], "model_id": binding["model"]["model_id"],
        "selection": binding["model"]["selection"], "model_observed": obj.get("model"),
        "model_observation_basis": "provider_response" if obj.get("model") else "unavailable",
        "identity_status": "provider_reported" if obj.get("model") else "unavailable",
        "elapsed_ms": elapsed_ms, "usage": normalize_usage(usage),
        "usage_reported": usage, "response_id": obj.get("id"),
        "stop_reason": obj.get("stop_reason") or obj.get("status"),
        "observed_manifest_sha256": None,
        "does_not_prove": ["MODEL_WEIGHTS_IDENTITY", "SEMANTIC_TRUTH"]})


def _execute(call, executor, ledger, sign_key, meta, on_event, deadline):
    if time.monotonic() >= deadline:
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    res = executor.execute(call["name"], call["args"])
    ledger.append("tool_call", f"{call['name']} {json.dumps(call['args'], sort_keys=True)}", meta)
    extra = _edit_fingerprint(call["name"], call["args"], res, executor) if res.ok else None
    result_meta = dict(meta)
    if extra:
        result_meta.update(extra)
    ledger.append("tool_result", res.output, _result_meta(call["name"], res, sign_key, result_meta))
    if on_event:
        on_event({"type": "tool_call", "name": call["name"], "args": call["args"]})
        on_event({"type": "tool_result", "name": call["name"], "ok": res.ok,
                  "output": res.output[:500]})
    return res
