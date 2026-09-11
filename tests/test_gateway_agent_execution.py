"""Actual router and original ledger; only the model proposer is synthetic."""
import json
import time

from harness.credential_handles import CredentialBindings
from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_operation import canonicalize_operation
from harness.plan_run_snapshot import thaw_json

import pytest

from harness.gateway_agent_trace import AgentTrace
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_secret_boundary import validate_no_raw_secrets
from harness.local_session import SessionLedger, Entry

OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32
MARKER = "PRIVATE_SELECTED_SOURCE_FIXTURE_b392a"


def operation(tmp_path):
    return {"goal": MARKER, "endpoint": "ollama", "model": "qwen2.5-coder:14b", "root": str(tmp_path),
        "max_steps": 3, "allow_write": False, "allow_exec": False,
        "stream": True, "data_refs": [], "credential_refs": []}


def run_bound(operation, bindings, root, writer, emitted):
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", operation), root))
    return run_private_agent(operation, bindings, root, writer, None, emitted,
        binding=binding, deadline=time.monotonic() + binding["budget"]["timeout_s"])


@pytest.mark.parametrize("mode", ["final", "error"])
def test_actual_router_keeps_source_final_and_errors_out_of_public_sinks(tmp_path, monkeypatch, mode):
    def transport_factory(**authority):
        def transport(method, url, headers, body, timeout):
            payload = json.loads(body)
            assert MARKER in json.dumps(payload["messages"])
            assert payload["model"] == authority["model"]
            assert payload["max_tokens"] == authority["max_tokens"]
            if mode == "error":
                raise RuntimeError(MARKER)
            return 200, {"model": authority["model"], "choices": [
                {"message": {"content": MARKER + " final answer"}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", transport_factory)
    def forbidden(*args, **kwargs):
        pytest.fail("private content reached a public scaffold/history sink")
    monkeypatch.setattr("harness.eval_store.save_agent_run", forbidden)
    monkeypatch.setattr("harness.scaffold.scaffold_answer", forbidden)
    monkeypatch.setattr("harness.gateway._countersign_run", forbidden)
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    emitted = []
    if mode == "error":
        with pytest.raises(RuntimeError):
            run_bound(operation(tmp_path), {}, tmp_path, writer, emitted.append)
        result = writer.projection("failed", reason="EXTERNAL_ACTION_FAILED")
    else:
        result = run_bound(operation(tmp_path), {}, tmp_path, writer, emitted.append)
    assert MARKER not in json.dumps([result, emitted])
    validate_no_raw_secrets(result)
    records = AgentTrace(tmp_path, OWNER, JOURNEY, OP).read()
    ledger = SessionLedger([Entry(**r["payload"]) for r in records if r["kind"] == "ledger"])
    assert ledger.verify() and MARKER in ledger.to_jsonl()
    assert not (tmp_path / "agent_runs").exists()
    if mode == "final":
        original = records[-1]["payload"]
        assert original["final"].startswith(MARKER)
        assert original["environment"]["python"]
        assert [json.loads(row) for row in original["ledger_jsonl"].splitlines()] == [
            json.loads(row) for row in ledger.to_jsonl().splitlines()]
        witness = next(r["payload"]["meta"] for r in records
                       if r["kind"] == "ledger" and r["payload"]["kind"] == "model_call")
        assert witness["requested_model_reference"] == "qwen2.5-coder:14b"
        assert witness["model_observed"] == "qwen2.5-coder:14b"
        assert witness["identity_status"] == "matched"
        assert witness["model_observation_basis"] == "provider_response"
        assert result["state"] == "completed"


def test_approved_binding_uses_value_for_without_ambient_fallback(tmp_path, monkeypatch):
    marker = "APPROVED_SYNTHETIC_KEY_739ab"
    seen = []
    original_value_for = CredentialBindings.value_for
    def value_for(self, slot):
        assert slot == "OPENAI_API_KEY"
        value = original_value_for(self, slot)
        seen.append(value)
        return value
    def factory(**authority):
        def transport(method, url, headers, body, timeout):
            assert headers["Authorization"] == "Bearer " + marker
            assert json.loads(body)["model"] == authority["model"]
            return 200, {"model": authority["model"], "choices": [
                {"message": {"content": "done"}}]}
        return transport
    monkeypatch.setattr(CredentialBindings, "value_for", value_for)
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "AMBIENT_SYNTHETIC_KEY_MUST_NOT_BE_USED")
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=(marker,))
    selected = {**operation(tmp_path), "endpoint": "openai", "model": "gpt-4o-mini"}
    run_bound(selected, {"OPENAI_API_KEY": marker}, tmp_path, writer, lambda _: None)
    assert seen == [marker]
    assert marker not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))
