"""Provider-native tool contracts for bound supervised agent runs."""
from __future__ import annotations

import time
from types import SimpleNamespace

from .evidence_json import canonical_sha256
from .gateway_agent_native_runtime import (
    execute_native_test_command,
    run_native_protocol_loop,
)
from .gateway_agent_transport import BoundAgentTransport
from .gateway_operation import GatewayOperationError
from .local_loop import _done
from .local_tools import ToolExecutor, ToolGate
from .router_agent import _finalize_run, _workspace_pre
from .tool_sandbox_bridge import fallback_from_env, make_sandboxed_runner

TOOL_PROTOCOL_SCHEMA = "flywheel.gateway-agent-tool-protocol/v1"
NATIVE_ROUTES = {"openai": "openai_responses", "anthropic": "anthropic_messages"}


def native_route(endpoint: dict) -> str:
    if (endpoint["adapter"] == "openai" and endpoint["name"] in {"openai", "codex"}
            and endpoint["base_url"] == "https://api.openai.com/v1" and not endpoint["local"]):
        return "openai_responses"
    if endpoint["adapter"] == "anthropic" and not endpoint["local"]:
        return "anthropic_messages"
    raise GatewayOperationError("AGENT_NATIVE_TOOL_UNSUPPORTED")


def native_tool_schemas(gate: ToolGate) -> list[dict]:
    def tool(name, description, props):
        return {"type": "function", "name": name, "description": description,
            "strict": True, "parameters": {"type": "object",
                "properties": props, "required": list(props),
                "additionalProperties": False}}
    text = {"type": "string"}
    tools = [
        tool("read_file", "Read a UTF-8 file under the approved workspace.", {"path": text}),
        tool("list_dir", "List one directory under the approved workspace.", {"path": text}),
        tool("grep", "Search files under the approved workspace.",
             {"pattern": text, "path": text, "glob": text}),
    ]
    if gate.allow_write:
        tools += [
            tool("write_file", "Write a UTF-8 file under the approved workspace.",
                 {"path": text, "content": text}),
            tool("edit_file", "Replace one exact string in an approved file.",
                 {"path": text, "old": text, "new": text}),
            tool("apply_patch", "Apply a strict unified diff under the workspace.",
                 {"patch": text}),
        ]
    if gate.allow_exec:
        tools.append(tool("run", "Run a bounded command under the approved workspace.",
                          {"cmd": text}))
    return tools


def native_tool_contract(capabilities: dict, endpoint: dict) -> dict:
    gate = ToolGate(capabilities["allow_write"], capabilities["allow_exec"], False)
    tools = native_tool_schemas(gate)
    return {"schema": TOOL_PROTOCOL_SCHEMA, "protocol": "native",
        "native_api_route": native_route(endpoint),
        "tool_schema_sha256": canonical_sha256({"tools": tools}),
        "tool_names": [t["name"] for t in tools], "strict_schemas": True,
        "parallel_tool_calls": False,
        "result_order_policy": "provider_order_sequential"}


def text_tool_contract() -> dict:
    return {"schema": TOOL_PROTOCOL_SCHEMA, "protocol": "text",
        "native_api_route": None, "tool_schema_sha256": None,
        "tool_names": [], "strict_schemas": False, "parallel_tool_calls": False,
        "result_order_policy": "text_tool_loop"}


def validate_openai_strict_tools(tools: list[dict]) -> dict[str, dict]:
    result = {}
    try:
        for tool in tools:
            params = tool["parameters"]
            props = params["properties"]
            if (tool.get("type") != "function" or tool.get("strict") is not True
                    or type(tool.get("name")) is not str or not tool["name"]
                    or params.get("type") != "object"
                    or params.get("additionalProperties") is not False
                    or set(params.get("required", ())) != set(props)
                    or any(type(k) is not str for k in props)):
                raise ValueError
            result[tool["name"]] = props
        if len(result) != len(tools):
            raise ValueError
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None
    return result


def run_native_tool_agent(goal: str, binding: dict, credentials, root, ledger,
                          deadline: float, *, on_event=None, test_cmd=None) -> dict:
    endpoint = binding["endpoint"]
    contract = binding["tool_protocol"]
    gate = ToolGate(binding["capabilities"]["allow_write"],
                    binding["capabilities"]["allow_exec"], False)
    tools = native_tool_schemas(gate)
    if canonical_sha256({"tools": tools}) != contract["tool_schema_sha256"]:
        raise GatewayOperationError("AGENT_BINDING_DRIFT")
    props = validate_openai_strict_tools(tools)
    slot = endpoint["slot"]
    key = credentials.value_for(slot) if slot else ""
    transport = BoundAgentTransport(base_url=endpoint["base_url"],
        adapter=endpoint["adapter"], model=binding["model"]["model_id"],
        deadline=deadline, max_tokens=binding["budget"]["max_tokens"],
        max_calls=binding["transport"]["max_requests"],
        native_protocol=contract["native_api_route"],
        allow_omitted_temperature=contract["native_api_route"] == "anthropic_messages")
    executor = ToolExecutor(root=str(root), gate=gate,
        runner=make_sandboxed_runner(bindings=credentials,
                                     on_unavailable=fallback_from_env()))
    if hasattr(executor, "init_receipt_chain"):
        executor.init_receipt_chain(f"run-{ledger.checkpoint()[:12]}")
    pre_state = _workspace_pre(str(root), gate.allow_write or gate.allow_exec, ledger)
    started = time.perf_counter()
    from . import tool_receipts
    sign_key = tool_receipts.new_session_key()
    ledger.append("user", goal)
    final, steps = run_native_protocol_loop(contract["native_api_route"], goal,
        binding, key, transport, executor, ledger, sign_key, deadline, on_event,
        tools, props)
    tests_pass = None
    if test_cmd:
        tests_pass = execute_native_test_command(
            test_cmd, executor, ledger, sign_key, on_event, deadline).ok
    result = _done(final, steps, ledger, tests_pass=tests_pass,
                   system="provider-native tool loop", goal=goal)
    return _finalize_run(result, endpoint=endpoint["name"],
        agent=SimpleNamespace(last_compaction=None), executor=executor,
        receipt_dir=None, duration=round(time.perf_counter() - started, 3),
        sign_key=sign_key, pre_state=pre_state, root=str(root), ledger=ledger)
