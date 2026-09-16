"""Execution-path coverage for reviewed MCP admission."""
import json
import time

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_operation import canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_agent_mcp_admission import (
    OWNER, agent_op, cache_synthetic_receipt, selection_admission,
)


def _binding(tmp_path, monkeypatch, *, tool_protocol=None):
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    operation = agent_op(tmp_path, selection_admission(receipt),
                         tool_protocol=tool_protocol)
    if tool_protocol == "native":
        operation.update(endpoint="openai", model="gpt-6-astra", max_tokens=128)
    return operation, thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", operation), tmp_path / "workspace",
        owner_ref=OWNER, state_root=tmp_path / "state"))


def test_catalog_stdio_runtime_bridges_text_tool_loop(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_admission import open_mcp_runtime
    from harness.proposer import ProposerOutput
    from harness.router_agent import run_router_agent

    _operation, binding = _binding(tmp_path, monkeypatch)
    events, replies = [], ['TOOL mcp_synthetic__echo {"msg":"text"}', "done"]

    class Proposer:
        def generate(self, _prompt, **_kwargs):
            return ProposerOutput(replies.pop(0), "stub", 0, "hash", "test")

    with open_mcp_runtime(binding["mcp_admission"], root=tmp_path / "workspace",
                          deadline=time.monotonic() + 15,
                          on_event=events.append) as runtime:
        result = run_router_agent("use echo", "stub", root=str(tmp_path / "workspace"),
            proposer=Proposer(), allow_mcp=runtime["allow_mcp"],
            external=runtime["external"], max_steps=3)
    assert result["final"] == "done"
    assert "echo: text" in result["ledger_jsonl"]
    assert events[0]["type"] == "mcp_runtime_validated"
    assert events[0]["servers"][0]["discovery_receipt_sha256"]


def test_native_api_tool_path_receives_and_executes_admitted_mcp_tool(tmp_path, monkeypatch):
    from harness.gateway_agent_execution import run_private_agent
    from harness.gateway_agent_trace import AgentTrace

    operation, binding = _binding(tmp_path, monkeypatch, tool_protocol="native")
    calls = []

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, _method, _url, _headers, body, _timeout):
            payload = json.loads(body); calls.append(payload)
            if len(calls) == 1:
                assert "mcp_synthetic__echo" in [tool["name"] for tool in payload["tools"]]
                return 200, {"id": "resp_1", "model": "gpt-6-astra",
                    "status": "completed", "output": [{"type": "function_call",
                    "id": "fc_1", "call_id": "call_1", "name": "mcp_synthetic__echo",
                    "arguments": json.dumps({"msg": "native"})}]}
            assert "echo: native" in calls[1]["input"][-1]["output"]
            return 200, {"id": "resp_2", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "message",
                "content": [{"type": "output_text", "text": "done"}]}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, "jrn_" + "b" * 32, "op_" + "c" * 32)
    result = run_private_agent(operation, {"OPENAI_API_KEY": "OPENAI_KEY"},
        tmp_path, trace, None, lambda _event: None, binding=binding,
        deadline=time.monotonic() + 15)
    assert result["state"] == "completed"
    assert len(calls) == 2
