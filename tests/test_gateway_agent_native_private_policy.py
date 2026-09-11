"""Native provider private-boundary parity controls."""
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from harness.proposer import ProposerOutput, prompt_hash
from tests.test_gateway_agent_native_tools import (
    JOURNEY,
    OP,
    OWNER,
    ledger_rows,
    native_binding,
    native_operation,
)

SAFE_LONG_TEXT = "L" * 70_000
SPANNING_SECRET = "S" * 59_990 + "Authorization: Bearer SYNTHETIC_UNBOUND_CREDENTIAL"


class LongLegacyProposer:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(SAFE_LONG_TEXT, "fake-openai", seed,
            prompt_hash(prompt), "test", served_model="gpt-6-astra")


def legacy_binding(tmp_path):
    op = native_operation(tmp_path, max_tokens=32768)
    op.pop("tool_protocol")
    canonical = canonicalize_operation("agent.run", op)
    return op, thaw_json(freeze_agent_binding(canonical, tmp_path))


def test_native_and_legacy_accept_safe_long_private_text(tmp_path, monkeypatch):
    legacy_op, legacy = legacy_binding(tmp_path)
    monkeypatch.setattr("harness.gateway_agent_proposer.BoundAgentProposer",
                        LongLegacyProposer)
    legacy_trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("OPENAI_KEY",))
    legacy_result = run_private_agent(legacy_op, {"OPENAI_API_KEY": "OPENAI_KEY"},
        tmp_path, legacy_trace, None, lambda event: None, binding=legacy,
        deadline=time.monotonic() + 15)

    native_op, native = native_binding(tmp_path, max_tokens=32768)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_long", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "message",
                "content": [{"type": "output_text", "text": SAFE_LONG_TEXT}]}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    native_trace = AgentTrace(tmp_path, OWNER, JOURNEY, "op_" + "d" * 32,
                              secrets=("OPENAI_KEY",))
    native_result = run_private_agent(native_op, {"OPENAI_API_KEY": "OPENAI_KEY"},
        tmp_path, native_trace, None, lambda event: None, binding=native,
        deadline=time.monotonic() + 15)

    assert legacy_result["state"] == "completed"
    assert native_result["state"] == "completed"
    assert SAFE_LONG_TEXT in json.dumps(legacy_trace.read())
    assert SAFE_LONG_TEXT in json.dumps(native_trace.read())
    assert SAFE_LONG_TEXT not in json.dumps(legacy_result)
    assert SAFE_LONG_TEXT not in json.dumps(native_result)


def test_native_spanning_window_secret_rejected_before_write(tmp_path, monkeypatch):
    op, binding = native_binding(tmp_path, allow_write=True, max_tokens=32768)

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["native_protocol"] == "openai_responses"
        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_spanning", "model": "gpt-6-astra",
                "status": "completed", "output": [{"type": "function_call",
                "id": "fc_1", "call_id": "call_1", "name": "write_file",
                "arguments": json.dumps({"path": "spanning.txt",
                    "content": SPANNING_SECRET})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    with pytest.raises(GatewayOperationError, match="AGENT_NATIVE_PROTOCOL_ERROR"):
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path,
            trace, None, lambda event: None, binding=binding,
            deadline=time.monotonic() + 15)
    assert not (tmp_path / "spanning.txt").exists()
    assert ledger_rows(trace, "tool_call") == []
    assert "SYNTHETIC_UNBOUND_CREDENTIAL" not in json.dumps(trace.read())
