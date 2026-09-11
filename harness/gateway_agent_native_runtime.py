"""Provider-native turn loops for bound supervised agent runs."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import time
from copy import deepcopy

from .evidence_json import canonical_sha256
from .gateway_agent_native_validation import (
    anthropic_calls, anthropic_terminal_guard, anthropic_text, anthropic_tools,
    openai_calls, openai_terminal_guard, openai_text, provider_response_content,
    provider_response_meta, reject_private_value,
)
from .gateway_operation import GatewayOperationError
from .local_loop import _edit_fingerprint, _result_meta
from .proposer import normalize_usage


def run_native_protocol_loop(route, goal, binding, key, transport, executor,
                             ledger, sign_key, deadline, on_event, tools, props,
                             private_guard=None):
    if route == "openai_responses":
        return _openai_loop(goal, binding, key, transport, executor, ledger,
                            sign_key, deadline, on_event, tools, props, private_guard)
    if route == "anthropic_messages":
        return _anthropic_loop(goal, binding, key, transport, executor, ledger,
                               sign_key, deadline, on_event, tools, props, private_guard)
    raise GatewayOperationError("AGENT_BINDING_DRIFT")


def execute_native_test_command(test_cmd, executor, ledger, sign_key,
                                on_event, deadline, private_guard=None):
    return _execute({"name": "run", "args": {"cmd": test_cmd},
        "provider_call_id": "test_cmd", "provider_item_id": "test_cmd",
        "provider_order_index": 0}, executor, ledger, sign_key,
        {"native_block": False, "gate": "test"}, on_event, deadline, private_guard)


def _openai_loop(goal, binding, key, transport, executor, ledger, sign_key,
                 deadline, on_event, tools, props, private_guard):
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    url = binding["endpoint"]["base_url"] + "/responses"
    input_items, used = [{"role": "user", "content": goal}], set()
    for step in range(1, binding["budget"]["max_steps"] + 1):
        payload = {"model": binding["model"]["model_id"], "input": input_items,
            "max_output_tokens": binding["budget"]["max_tokens"], "store": False,
            "parallel_tool_calls": False, "tools": tools, "stream": False,
            "temperature": 0}
        obj = _call("openai_responses", binding, transport, url, payload, headers,
                    ledger, step, deadline, private_guard)
        openai_terminal_guard(obj)
        output = obj.get("output")
        if not isinstance(output, list):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        calls = openai_calls(output, props, used)
        _reject_call_secrets(calls, private_guard)
        if not calls:
            text = openai_text(output)
            ledger.append("assistant", text, {"backend": binding["endpoint"]["name"],
                "native_api_route": "openai_responses", "response_id": obj.get("id")})
            return text, step
        results = []
        for call in calls:
            res = _execute(call, executor, ledger, sign_key, _call_meta(
                "openai_responses", obj, call), on_event, deadline, private_guard)
            results.append({"type": "function_call_output",
                "call_id": call["provider_call_id"], "output": res.output})
        input_items.extend(deepcopy(output))
        input_items.extend(results)
    return "[max_steps reached without a final answer]", binding["budget"]["max_steps"]


def _anthropic_loop(goal, binding, key, transport, executor, ledger, sign_key,
                    deadline, on_event, tools, props, private_guard):
    headers = {"Content-Type": "application/json", "x-api-key": key,
               "anthropic-version": "2023-06-01"}
    url = binding["endpoint"]["base_url"] + "/v1/messages"
    messages, used = [{"role": "user", "content": goal}], set()
    for step in range(1, binding["budget"]["max_steps"] + 1):
        payload = {"model": binding["model"]["model_id"], "messages": messages,
            "max_tokens": binding["budget"]["max_tokens"],
            "tools": anthropic_tools(tools), "stream": False,
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True}}
        obj = _call("anthropic_messages", binding, transport, url, payload, headers,
                    ledger, step, deadline, private_guard)
        anthropic_terminal_guard(obj)
        content = obj.get("content")
        if not isinstance(content, list):
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        calls = anthropic_calls(content, props, used)
        _reject_call_secrets(calls, private_guard)
        if not calls:
            text = anthropic_text(content)
            ledger.append("assistant", text, {"backend": binding["endpoint"]["name"],
                "native_api_route": "anthropic_messages", "response_id": obj.get("id")})
            return text, step
        messages.append({"role": "assistant", "content": deepcopy(content)})
        blocks = []
        for call in calls:
            res = _execute(call, executor, ledger, sign_key, _call_meta(
                "anthropic_messages", obj, call), on_event, deadline, private_guard)
            blocks.append({"type": "tool_result", "tool_use_id": call["provider_call_id"],
                           "content": res.output, "is_error": not res.ok})
        messages.append({"role": "user", "content": blocks})
    return "[max_steps reached without a final answer]", binding["budget"]["max_steps"]


def _call(route, binding, transport, url, payload, headers, ledger, ordinal,
          deadline, private_guard):
    if time.monotonic() >= deadline:
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    started = time.monotonic()
    _inference(ledger, binding, ordinal, "started", None, None)
    try:
        status, obj = transport("POST", url, headers,
            json.dumps(payload, separators=(",", ":")).encode(), binding["budget"]["timeout_s"])
        elapsed = int(max(0, (time.monotonic() - started) * 1000))
        if not 200 <= status < 300:
            ledger.append("provider_error", "", _provider_error_meta(status, obj, private_guard))
            _inference(ledger, binding, ordinal, "failed", elapsed, "EXTERNAL_ACTION_FAILED")
            raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
        if not isinstance(obj, dict):
            _inference(ledger, binding, ordinal, "failed", elapsed, "AGENT_NATIVE_PROTOCOL_ERROR")
            raise GatewayOperationError("AGENT_NATIVE_PROTOCOL_ERROR")
        try:
            reject_private_value(private_guard, obj)
        except GatewayOperationError:
            _inference(ledger, binding, ordinal, "failed", elapsed, "AGENT_NATIVE_PROTOCOL_ERROR")
            raise
        _inference(ledger, binding, ordinal, "response_received", elapsed, None)
        content = provider_response_content(route, obj)
        reject_private_value(private_guard, content)
        ledger.append("provider_response", json.dumps(content, sort_keys=True),
                      provider_response_meta(route, binding, ordinal, obj))
        _model_call(ledger, binding, ordinal, obj, elapsed)
        return obj
    except GatewayOperationError:
        raise
    except Exception:
        _inference(ledger, binding, ordinal, "failed",
                   int(max(0, (time.monotonic() - started) * 1000)),
                   "EXTERNAL_ACTION_FAILED")
        raise


def _provider_error_meta(status, obj, private_guard):
    meta = {"status": status}
    try:
        reject_private_value(private_guard, obj)
        meta["response"] = obj
    except GatewayOperationError:
        meta["response_omitted_reason"] = "secret_boundary"
    return meta


def _reject_call_secrets(calls, private_guard):
    for call in calls:
        reject_private_value(private_guard, call["args"])


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


def _execute(call, executor, ledger, sign_key, meta, on_event, deadline, private_guard):
    if time.monotonic() >= deadline:
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    reject_private_value(private_guard, call["args"])
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
