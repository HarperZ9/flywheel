"""End-to-end native provider tool-turn controls."""
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_agent_transport import AgentTransportError, BoundAgentTransport
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_agent_transport import server


OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32


def native_operation(tmp_path, endpoint="openai", model="gpt-6-astra", **changes):
    data = dict(goal="read fixture", endpoint=endpoint, model=model,
        root=str(tmp_path), max_steps=4, max_tokens=321, timeout_s=15,
        allow_write=False, allow_exec=False, stream=True,
        tool_protocol="native", data_refs=[], credential_refs=[])
    data.update(changes)
    return data


def native_binding(tmp_path, endpoint="openai", model="gpt-6-astra", **changes):
    op = native_operation(tmp_path, endpoint, model, **changes)
    canonical = canonicalize_operation("agent.run", op)
    binding = thaw_json(freeze_agent_binding(canonical, tmp_path))
    return op, binding


def ledger_rows(trace, kind):
    return [r["payload"] for r in trace.read()
            if r["kind"] == "ledger" and r["payload"]["kind"] == kind]


def test_native_binding_v2_freezes_protocol_schema_and_rejects_local_compat(tmp_path):
    op, binding = native_binding(tmp_path)
    assert binding["schema"] == "flywheel.gateway-agent-binding/v2"
    native = binding["tool_protocol"]
    assert native["protocol"] == "native"
    assert native["native_api_route"] == "openai_responses"
    assert native["result_order_policy"] == "provider_order_sequential"
    assert native["parallel_tool_calls"] is False
    assert "read_file" in native["tool_names"]
    assert native["tool_schema_sha256"] == thaw_json(
        freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path)
    )["tool_protocol"]["tool_schema_sha256"]

    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_TOOL_UNSUPPORTED"):
        native_binding(tmp_path, endpoint="ollama", model="telos-coder-14b")


def test_openai_responses_two_turn_uses_exact_call_id_and_no_text_rescue(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("OPENAI_NATIVE_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path)
    captured = []
    first_output = [
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "OPAQUE"},
        {"type": "function_call", "id": "fc_1",
         "call_id": "call_1", "name": "read_file",
         "arguments": json.dumps({"path": "fixture.txt"})},
        {"type": "message", "role": "assistant",
         "content": [{"type": "output_text",
                      "text": 'TOOL read_file {"path":"fixture.txt"}'}]},
    ]

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
            assert kwargs["model"] == "gpt-6-astra"

        def __call__(self, method, url, headers, body, timeout):
            payload = json.loads(body)
            captured.append((url, payload))
            assert url.endswith("/responses")
            if len(captured) == 1:
                return 200, {"id": "resp_1", "model": "gpt-6-astra",
                    "status": "completed", "output": first_output,
                    "usage": {"input_tokens": 4, "output_tokens": 5,
                                 "total_tokens": 9}}
            assert payload["input"][:3] == first_output
            assert payload["input"][3]["type"] == "function_call_output"
            assert payload["input"][3]["call_id"] == "call_1"
            assert "OPENAI_NATIVE_READBACK" in payload["input"][3]["output"]
            return 200, {"id": "resp_2", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "done"}]}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("OPENAI_KEY",))
    result = run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
        trace, None, lambda event: None, binding=binding,
        deadline=time.monotonic() + 15)

    assert result["state"] == "completed"
    assert len(captured) == 2
    assert captured[0][1]["store"] is False
    assert captured[0][1]["parallel_tool_calls"] is False
    assert "previous_response_id" not in captured[1][1]
    tools = ledger_rows(trace, "tool_call")
    assert len(tools) == 1
    assert tools[0]["meta"]["provider_call_id"] == "call_1"
    assert tools[0]["meta"]["native_block"] is True
    assert json.dumps(result).find("OPENAI_NATIVE_READBACK") == -1


def test_absent_protocol_keeps_v1_and_explicit_text_is_bound_compat(tmp_path):
    legacy = dict(goal="fixture", endpoint="ollama", root=str(tmp_path),
        max_steps=2, allow_write=False, allow_exec=False, stream=True,
        data_refs=[], credential_refs=[])
    legacy_binding = thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", legacy), tmp_path))
    assert legacy_binding["schema"] == "flywheel.gateway-agent-binding/v1"
    assert "tool_protocol" not in legacy_binding

    compat = dict(legacy, tool_protocol="text")
    compat_binding = thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", compat), tmp_path))
    assert compat_binding["schema"] == "flywheel.gateway-agent-binding/v2"
    assert compat_binding["tool_protocol"]["protocol"] == "text"


def test_native_review_v2_exposes_frozen_protocol(tmp_path):
    from harness.gateway_agent_grant import review_binding
    _, binding = native_binding(tmp_path)
    review = review_binding({"agent_binding": binding})
    assert review["schema"] == "flywheel.gateway-agent-review/v2"
    assert review["tool_protocol"] == binding["tool_protocol"]
    assert review["tool_protocol"]["native_api_route"] == "openai_responses"


def test_anthropic_messages_tool_result_is_adjacent_and_ordered(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("ANTHROPIC_NATIVE_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path, endpoint="anthropic", model="claude-sonnet-5")
    captured = []

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "anthropic_messages"

        def __call__(self, method, url, headers, body, timeout):
            payload = json.loads(body)
            captured.append(payload)
            assert url.endswith("/v1/messages")
            assert "temperature" not in payload
            if len(captured) == 1:
                return 200, {"id": "msg_1", "model": "claude-sonnet-5",
                    "stop_reason": "tool_use", "content": [
                        {"type": "text", "text": "checking"},
                        {"type": "tool_use", "id": "toolu_1",
                         "name": "read_file", "input": {"path": "fixture.txt"}},
                    ]}
            messages = payload["messages"]
            assert messages[-2]["role"] == "assistant"
            assert messages[-2]["content"][1]["id"] == "toolu_1"
            assert messages[-1]["role"] == "user"
            assert messages[-1]["content"][0]["type"] == "tool_result"
            assert messages[-1]["content"][0]["tool_use_id"] == "toolu_1"
            assert "ANTHROPIC_NATIVE_READBACK" in messages[-1]["content"][0]["content"]
            return 200, {"id": "msg_2", "model": "claude-sonnet-5",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "done"}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    result = run_private_agent(op, {"ANTHROPIC_API_KEY": "ANTHROPIC_KEY"},
        tmp_path, trace, None, lambda event: None, binding=binding,
        deadline=time.monotonic() + 15)

    assert result["state"] == "completed"
    assert len(captured) == 2
    assert ledger_rows(trace, "tool_call")[0]["meta"]["provider_call_id"] == "toolu_1"


def test_native_openai_schema_rejects_loose_schema_before_http(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path)
    loose = [{"type": "function", "name": "loose",
        "strict": True, "parameters": {"type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": True}}]
    monkeypatch.setattr("harness.gateway_agent_native_tools.native_tool_schemas",
        lambda gate: loose)
    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport",
        lambda **_: pytest.fail("loose schema reached HTTP"))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_BINDING_DRIFT"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)


def test_native_transport_responses_route_and_extra_fields_are_bound():
    payload = {"model": "selected", "input": [{"role": "user", "content": "hi"}],
        "max_output_tokens": 32, "store": False, "parallel_tool_calls": False,
        "tools": [], "stream": False, "temperature": 0}
    with server() as (origin, requests):
        call = BoundAgentTransport(base_url=origin, adapter="openai",
            model="selected", deadline=time.monotonic() + 5, max_tokens=32,
            max_calls=2, native_protocol="openai_responses")
        assert call("POST", origin + "/responses",
            {"Content-Type": "application/json", "Authorization": "Bearer x"},
            json.dumps(payload).encode(), 3)[0] == 200
        assert requests[0][0] == "/responses"
    payload["top_p"] = 1
    with pytest.raises(AgentTransportError, match="AGENT_BINDING_DRIFT"):
        call("POST", origin + "/responses",
            {"Content-Type": "application/json", "Authorization": "Bearer x"},
            json.dumps(payload).encode(), 3)
