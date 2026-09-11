"""Negative controls for provider-native agent tool turns."""
import json
import time
from copy import deepcopy

import pytest

from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError
from tests.test_gateway_agent_native_tools import (
    JOURNEY,
    OP,
    OWNER,
    ledger_rows,
    native_binding,
)


def test_native_duplicate_id_fails_before_repeat_side_effect(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("DUPLICATE_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_dup", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                     "name": "read_file", "arguments": json.dumps({"path": "fixture.txt"})},
                    {"type": "function_call", "id": "fc_2", "call_id": "call_1",
                     "name": "read_file", "arguments": json.dumps({"path": "fixture.txt"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert ledger_rows(trace, "tool_call") == []


def test_anthropic_max_tokens_fails_without_tool_execution(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, endpoint="anthropic", model="claude-sonnet-5")

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "anthropic_messages"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "msg_truncated", "model": "claude-sonnet-5",
                "stop_reason": "max_tokens", "content": [
                    {"type": "tool_use", "id": "toolu_1",
                     "name": "read_file", "input": {"path": "fixture.txt"}}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_INCOMPLETE"):
        run_private_agent(op, {"ANTHROPIC_API_KEY": "ANTHROPIC_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert ledger_rows(trace, "tool_call") == []


def test_openai_malformed_second_response_fails_after_one_tool(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("READ_ONCE", encoding="utf-8")
    op, binding = native_binding(tmp_path)
    calls = 0

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return 200, {"id": "resp_1", "model": "gpt-6-astra",
                    "status": "completed", "output": [
                        {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                         "name": "read_file", "arguments": json.dumps({"path": "fixture.txt"})}]}
            return 200, {"id": "resp_2", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "reasoning", "id": "rs_2",
                "encrypted_content": "OPAQUE"}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert len(ledger_rows(trace, "tool_call")) == 1


def test_native_binding_protocol_drift_denies_before_credentials(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path)
    drifted = deepcopy(binding)
    drifted["tool_protocol"]["native_api_route"] = "anthropic_messages"

    def credential_bomb(*args, **kwargs):
        pytest.fail("credential materialized after binding drift")

    monkeypatch.setattr("harness.gateway_agent_execution.CredentialBindings", credential_bomb)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_BINDING_DRIFT"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=drifted,
            deadline=time.monotonic() + 15)
