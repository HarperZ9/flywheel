"""Provider-native agent runs over real bounded HTTP transport."""
import json
import time

from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from tests.native_provider_http_fixture import native_provider_server
from tests.test_gateway_agent_native_tools import (
    JOURNEY,
    OP,
    OWNER,
    ledger_rows,
    native_binding,
)


def test_openai_native_http_accumulates_store_false_replay(tmp_path, monkeypatch):
    (tmp_path / "one.txt").write_text("ONE_HTTP_READBACK", encoding="utf-8")
    (tmp_path / "two.txt").write_text("TWO_HTTP_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path)
    first = [{"type": "message", "id": "msg_visible", "content": [
        {"type": "output_text", "text": "INTERMEDIATE_HTTP_VISIBLE"}]},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1",
         "name": "read_file", "arguments": json.dumps({"path": "one.txt"})}]
    second = [{"type": "reasoning", "id": "rs_2", "encrypted_content": "OPAQUE"},
        {"type": "function_call", "id": "fc_2", "call_id": "call_2",
         "name": "read_file", "arguments": json.dumps({"path": "two.txt"})}]
    responses = [
        {"id": "resp_1", "model": "gpt-6-astra", "status": "completed",
         "output": first},
        {"id": "resp_2", "model": "gpt-6-astra", "status": "completed",
         "output": second},
        {"id": "resp_3", "model": "gpt-6-astra", "status": "completed",
         "output": [{"type": "message", "content": [
             {"type": "output_text", "text": "done"}]}]},
    ]
    with native_provider_server(responses) as (_, requests, opener):
        monkeypatch.setattr("harness.gateway_agent_native_tools._native_transport_opener",
                            lambda: opener)
        trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("OPENAI_KEY",))
        result = run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"},
            tmp_path, trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)

    bodies = [json.loads(row[2]) for row in requests]
    assert result["state"] == "completed"
    assert [row[0] for row in requests] == ["/v1/responses"] * 3
    assert opener.upstream_urls == ["https://api.openai.com/v1/responses"] * 3
    assert all("previous_response_id" not in body for body in bodies)
    assert bodies[1]["input"][0] == {"role": "user", "content": "read fixture"}
    assert bodies[1]["input"][1:3] == first
    assert bodies[1]["input"][3]["call_id"] == "call_1"
    assert "ONE_HTTP_READBACK" in bodies[1]["input"][3]["output"]
    expected = [{"role": "user", "content": "read fixture"}, *first,
        bodies[1]["input"][3], *second]
    assert bodies[2]["input"][:len(expected)] == expected
    assert bodies[2]["input"][-1]["call_id"] == "call_2"
    assert "TWO_HTTP_READBACK" in bodies[2]["input"][-1]["output"]
    assert [row["meta"]["provider_call_id"] for row in ledger_rows(trace, "tool_call")] == ["call_1", "call_2"]
    receipts = ledger_rows(trace, "provider_response")
    assert [row["meta"]["response_id"] for row in receipts] == ["resp_1", "resp_2", "resp_3"]
    assert receipts[1]["meta"]["response_bytes"] > 0
    assert {item["id"] for item in receipts[1]["meta"]["source_ids"]} >= {"resp_2", "rs_2", "fc_2", "call_2"}
    records = json.dumps(trace.read())
    assert "INTERMEDIATE_HTTP_VISIBLE" in records
    assert "encrypted_content" not in records
    assert "INTERMEDIATE_HTTP_VISIBLE" not in json.dumps(result)
    assert "ONE_HTTP_READBACK" not in json.dumps(result)


def test_anthropic_native_http_preserves_tool_result_adjacency(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("ANTHROPIC_HTTP_READBACK", encoding="utf-8")
    op, binding = native_binding(tmp_path, endpoint="anthropic", model="claude-sonnet-5")
    responses = [
        {"id": "msg_1", "model": "claude-sonnet-5", "stop_reason": "tool_use",
         "content": [{"type": "text", "text": "checking"},
             {"type": "tool_use", "id": "toolu_1", "name": "read_file",
              "input": {"path": "fixture.txt"}}]},
        {"id": "msg_2", "model": "claude-sonnet-5", "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "done"}]},
    ]
    with native_provider_server(responses) as (_, requests, opener):
        monkeypatch.setattr("harness.gateway_agent_native_tools._native_transport_opener",
                            lambda: opener)
        trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("ANTHROPIC_KEY",))
        result = run_private_agent(op, {"ANTHROPIC_API_KEY": "ANTHROPIC_KEY"},
            tmp_path, trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)

    bodies = [json.loads(row[2]) for row in requests]
    assert result["state"] == "completed"
    assert [row[0] for row in requests] == ["/v1/messages"] * 2
    assert opener.upstream_urls == ["https://api.anthropic.com/v1/messages"] * 2
    assert "temperature" not in bodies[0] and "temperature" not in bodies[1]
    assert bodies[0]["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert [tool["strict"] for tool in bodies[0]["tools"]] == [True, True, True]
    assert bodies[1]["messages"][-2]["content"][1]["id"] == "toolu_1"
    assert bodies[1]["messages"][-1]["content"][0]["tool_use_id"] == "toolu_1"
    assert bodies[1]["messages"][-1]["content"][0]["is_error"] is False
    assert "ANTHROPIC_HTTP_READBACK" in bodies[1]["messages"][-1]["content"][0]["content"]
    assert ledger_rows(trace, "tool_call")[0]["meta"]["provider_call_id"] == "toolu_1"


def test_anthropic_native_http_marks_tool_result_error(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, endpoint="anthropic", model="claude-sonnet-5")
    responses = [
        {"id": "msg_1", "model": "claude-sonnet-5", "stop_reason": "tool_use",
         "content": [{"type": "tool_use", "id": "toolu_1", "name": "read_file",
              "input": {"path": "absent.txt"}}]},
        {"id": "msg_2", "model": "claude-sonnet-5", "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "done"}]},
    ]
    with native_provider_server(responses) as (_, requests, opener):
        monkeypatch.setattr("harness.gateway_agent_native_tools._native_transport_opener",
                            lambda: opener)
        trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("ANTHROPIC_KEY",))
        result = run_private_agent(op, {"ANTHROPIC_API_KEY": "ANTHROPIC_KEY"},
            tmp_path, trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)

    bodies = [json.loads(row[2]) for row in requests]
    assert result["state"] == "completed"
    block = bodies[1]["messages"][-1]["content"][0]
    assert block == {"type": "tool_result", "tool_use_id": "toolu_1",
                     "content": "[error] read_file_open_failed", "is_error": True}
