"""Real router with synthetic provider responses and private identity witnesses."""
from dataclasses import replace
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import canonicalize_operation, GatewayOperationError
from harness.plan_run_snapshot import thaw_json

OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32


def setup(tmp_path, endpoint="ollama", model="selected/model:tag"):
    op = dict(goal="PRIVATE_BINDING_FIXTURE", endpoint=endpoint, model=model,
        root=str(tmp_path), max_steps=2, max_tokens=321, timeout_s=15,
        allow_exec=False, allow_write=False, stream=True, data_refs=[], credential_refs=[])
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))
    return op, binding, AgentTrace(tmp_path, OWNER, JOURNEY, OP)


def model_rows(trace):
    return [r["payload"]["meta"] for r in trace.read()
            if r["kind"] == "ledger" and r["payload"]["kind"] == "model_call"]


@pytest.mark.parametrize("observed", ["selected/model:tag", "different-model", None])
def test_actual_router_exact_model_reaches_adapter_and_mismatch_prevents_tool(tmp_path, monkeypatch, observed):
    op, binding, trace = setup(tmp_path)
    calls, emitted = [], []
    def transport_factory(**frozen):
        assert frozen["model"] == op["model"] and frozen["max_tokens"] == 321
        def transport(method, url, headers, body, timeout):
            payload = json.loads(body); calls.append(payload)
            assert payload["model"] == op["model"] and payload["max_tokens"] == 321
            return 200, {"model": observed, "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                "choices": [{"message": {"content": 'TOOL list_dir {"path":"."}'
                    if len(calls) == 1 else "PRIVATE_BINDING_FIXTURE final"}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", transport_factory)
    if observed == "different-model":
        monkeypatch.setattr("harness.local_tools.ToolExecutor.execute", lambda *a, **k: pytest.fail("mismatched model executed a tool"))
        with pytest.raises(GatewayOperationError, match="AGENT_MODEL_MISMATCH"):
            run_private_agent(op, {}, tmp_path, trace, None, emitted.append,
                binding=binding, deadline=time.monotonic() + 15)
        assert len(calls) == 1 and model_rows(trace)[0]["identity_status"] == "mismatch"
    else:
        result = run_private_agent(op, {}, tmp_path, trace, None, emitted.append,
            binding=binding, deadline=time.monotonic() + 15)
        assert result["state"] == "completed" and len(calls) == 2
        assert "PRIVATE_BINDING_FIXTURE" not in json.dumps([result, emitted])
        witness = model_rows(trace)[0]
        assert witness["requested_model_reference"] == op["model"]
        assert witness["model_observed"] == observed
        assert witness["identity_status"] == ("matched" if observed else "unavailable")
        assert witness["usage"] == {"prompt": 7, "completion": 3, "total": 10}
        assert witness["observed_manifest_sha256"] is None


@pytest.mark.parametrize("endpoint,raw", [
    ("openai", {"model": "provider-alias-2026", "choices": [{"message": {"content": "done"}}]}),
    ("anthropic", {"model": "provider-alias-2026", "content": [{"type": "text", "text": "done"}]}),
    ("gemini", {"modelVersion": "provider-alias-2026", "usageMetadata": {"promptTokenCount": 7},
                "candidates": [{"content": {"parts": [{"text": "done"}]}}]})])
def test_hosted_alias_and_native_observation_are_kept_without_false_mismatch(tmp_path, monkeypatch, endpoint, raw):
    op, binding, trace = setup(tmp_path, endpoint)
    marker = "SYNTHETIC_BOUND_CREDENTIAL_2839"
    def factory(**kwargs):
        def transport(method, url, headers, body, timeout):
            assert marker in headers.values() or "Bearer " + marker in headers.values()
            return 200, raw
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=(marker,))
    result = run_private_agent(op, {binding["endpoint"]["slot"]: marker}, tmp_path, trace, None,
        lambda event: None, binding=binding, deadline=time.monotonic() + 15)
    assert result["state"] == "completed"
    witness = model_rows(trace)[0]
    assert witness["model_observed"] == "provider-alias-2026"
    assert witness["identity_status"] == "provider_reported"
    if endpoint == "gemini": assert witness["usage_reported"] == raw["usageMetadata"]
    assert marker not in json.dumps(trace.read())


def test_consumed_snapshot_ignores_changed_registry_and_default_environment(tmp_path, monkeypatch):
    from harness.providers import REGISTRY
    op, binding, trace = setup(tmp_path)
    original = REGISTRY["ollama"]
    monkeypatch.setitem(REGISTRY, "ollama", replace(original, default_model="changed", base_url="http://invalid:1"))
    monkeypatch.setenv("OPENAI_BASE_URL", "http://invalid:2")
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(tmp_path / "forbidden"))
    def factory(**kwargs):
        assert kwargs["base_url"] == original.base_url
        return lambda *a: (200, {"model": op["model"], "choices": [{"message": {"content": "done"}}]})
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    assert run_private_agent(op, {}, tmp_path, trace, None, lambda event: None,
        binding=binding, deadline=time.monotonic() + 15)["state"] == "completed"


def test_missing_or_replaced_root_fails_before_provider(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    op, binding, _ = setup(workspace)
    state = tmp_path / "state"; state.mkdir()
    trace = AgentTrace(state, OWNER, JOURNEY, OP)
    workspace.rename(tmp_path / "previous"); workspace.mkdir()
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", lambda **kw: pytest.fail("root drift reached provider"))
    with pytest.raises(GatewayOperationError, match="AGENT_BINDING_DRIFT"):
        run_private_agent(op, {}, tmp_path, trace, None, lambda event: None,
            binding=binding, deadline=time.monotonic() + 15)


def test_error_response_cannot_supply_a_successful_model_observation(tmp_path, monkeypatch):
    op, binding, trace = setup(tmp_path)
    raw = {"model": op["model"], "usage": {"prompt_tokens": 9},
        "choices": [{"message": {"content": "wrong success"}}],
        "error": {"message": "PRIVATE_PROVIDER_ERROR_FIXTURE"}}
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport",
        lambda **kwargs: lambda *a: (400, raw))
    with pytest.raises(GatewayOperationError, match="EXTERNAL_ACTION_FAILED"):
        run_private_agent(op, {}, tmp_path, trace, None, lambda event: None,
            binding=binding, deadline=time.monotonic() + 15)
    witness = model_rows(trace)[0]
    assert witness["model_observed"] is None and witness["usage"] is None
    assert witness["model_observation_basis"] == "unavailable"
    errors = [r["payload"]["meta"] for r in trace.read()
        if r["kind"] == "ledger" and r["payload"]["kind"] == "provider_error"]
    assert errors == [{"status": 400, "response": raw}]
    assert "PRIVATE_PROVIDER_ERROR_FIXTURE" not in json.dumps(trace.projection("failed"))


def test_native_temperature_retry_preserves_only_successful_model_witness(tmp_path, monkeypatch):
    op, binding, trace = setup(tmp_path, "anthropic")
    calls = []
    monkeypatch.setattr("harness.endpoints._NO_TEMPERATURE", set())
    def factory(**kwargs):
        def transport(method, url, headers, body, timeout):
            calls.append(json.loads(body))
            if len(calls) == 1:
                return 400, {"model": "error-model", "error": {"message": "temperature is unsupported"}}
            return 200, {"model": "successful-provider-alias",
                         "content": [{"type": "text", "text": "done"}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    run_private_agent(op, {"ANTHROPIC_API_KEY": "synthetic"}, tmp_path, trace, None,
        lambda event: None, binding=binding, deadline=time.monotonic() + 15)
    assert calls[0]["temperature"] == 0 and "temperature" not in calls[1]
    assert model_rows(trace)[0]["model_observed"] == "successful-provider-alias"
    assert model_rows(trace)[0]["identity_status"] == "provider_reported"
