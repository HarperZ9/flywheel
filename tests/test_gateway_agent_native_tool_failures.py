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



def test_openai_refusal_plus_write_fails_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_refusal", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "message", "content": [
                        {"type": "refusal", "refusal": "blocked"}]},
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                     "name": "write_file", "arguments": json.dumps(
                         {"path": "blocked.txt", "content": "WRITE_AFTER_REFUSAL"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_REFUSAL"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert not (tmp_path / "blocked.txt").exists()
    assert ledger_rows(trace, "tool_call") == []


def test_openai_incomplete_function_call_item_fails_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_incomplete", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                     "status": "incomplete", "name": "write_file", "arguments": json.dumps(
                         {"path": "incomplete.txt", "content": "WRITE_FROM_INCOMPLETE_ITEM"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_INCOMPLETE"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert not (tmp_path / "incomplete.txt").exists()
    assert ledger_rows(trace, "tool_call") == []


def test_openai_empty_item_id_fails_before_tool(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("EMPTY_ID_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_empty", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "function_call", "id": "", "call_id": "call_1",
                     "name": "read_file", "arguments": json.dumps({"path": "fixture.txt"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert ledger_rows(trace, "tool_call") == []


def test_native_secret_argument_rejected_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_secret", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                     "name": "write_file", "arguments": json.dumps(
                         {"path": "secret.txt", "content": "SYNTHETIC_KEY_ONLY"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("SYNTHETIC_KEY_ONLY",))
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "SYNTHETIC_KEY_ONLY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    records = trace.read()
    assert "SYNTHETIC_KEY_ONLY" not in json.dumps(records)
    assert not (tmp_path / "secret.txt").exists()
    assert ledger_rows(trace, "provider_response") == []
    assert ledger_rows(trace, "tool_call") == []


def test_native_raw_secret_grammar_rejected_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)
    secret_like = "Authorization: Bearer SYNTHETIC_UNBOUND_CREDENTIAL"

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_secretish", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "function_call",
                "id": "fc_1", "call_id": "call_1", "name": "write_file",
                "arguments": json.dumps({"path": "secretish.txt", "content": secret_like})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert secret_like not in json.dumps(trace.read())
    assert not (tmp_path / "secretish.txt").exists()
    assert ledger_rows(trace, "tool_call") == []


def test_openai_duplicate_item_id_batch_fails_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_dup_item", "model": "gpt-6-astra",
                "status": "completed", "output": [
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                     "name": "write_file", "arguments": json.dumps({"path": "dup.txt", "content": "FIRST"})},
                    {"type": "function_call", "id": "fc_1", "call_id": "call_2",
                     "name": "write_file", "arguments": json.dumps({"path": "dup.txt", "content": "SECOND"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert not (tmp_path / "dup.txt").exists()
    assert ledger_rows(trace, "tool_call") == []


def test_openai_replayed_item_id_next_turn_fails_before_second_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True)
    calls = 0

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, method, url, headers, body, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return 200, {"id": "resp_1", "model": "gpt-6-astra",
                    "status": "completed", "output": [{"type": "function_call",
                    "id": "fc_1", "call_id": "call_1", "name": "write_file",
                    "arguments": json.dumps({"path": "replay.txt", "content": "FIRST"})}]}
            return 200, {"id": "resp_2", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "function_call",
                "id": "fc_1", "call_id": "call_2", "name": "write_file",
                "arguments": json.dumps({"path": "replay.txt", "content": "SECOND"})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert (tmp_path / "replay.txt").read_text(encoding="utf-8") == "FIRST"
    assert len(ledger_rows(trace, "tool_call")) == 1
