"""Actual router and original ledger; only the model proposer is synthetic."""
import json
from types import SimpleNamespace

import pytest

from harness.gateway_agent_trace import AgentTrace
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_secret_boundary import validate_no_raw_secrets
from harness.local_session import SessionLedger, Entry

OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32
MARKER = "PRIVATE_SELECTED_SOURCE_FIXTURE_b392a"


def operation(tmp_path):
    return {"goal": MARKER, "endpoint": "ollama", "root": str(tmp_path),
        "max_steps": 3, "allow_write": False, "allow_exec": False,
        "stream": True, "data_refs": [], "credential_refs": []}


@pytest.mark.parametrize("mode", ["final", "error"])
def test_actual_router_keeps_source_final_and_errors_out_of_public_sinks(tmp_path, monkeypatch, mode):
    class Proposer:
        def generate(self, prompt, **kwargs):
            assert MARKER in prompt
            if mode == "error":
                raise RuntimeError(MARKER)
            return SimpleNamespace(text=MARKER + " final answer", model_ref="fixture:model")
    monkeypatch.setattr("harness.router_agent.make_authorized_endpoint_proposer", lambda *a, **kw: Proposer())
    def forbidden(*args, **kwargs):
        pytest.fail("private content reached a public scaffold/history sink")
    monkeypatch.setattr("harness.eval_store.save_agent_run", forbidden)
    monkeypatch.setattr("harness.scaffold.scaffold_answer", forbidden)
    monkeypatch.setattr("harness.gateway._countersign_run", forbidden)
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    emitted = []
    if mode == "error":
        with pytest.raises(RuntimeError):
            run_private_agent(operation(tmp_path), {}, tmp_path, writer, None, emitted.append)
        result = writer.projection("failed", reason="EXTERNAL_ACTION_FAILED")
    else:
        result = run_private_agent(operation(tmp_path), {}, tmp_path, writer, None, emitted.append)
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
        assert original["ledger_jsonl"] == ledger.to_jsonl()
        assert result["state"] == "completed"


def test_approved_binding_uses_value_for_without_ambient_fallback(tmp_path, monkeypatch):
    marker = "APPROVED_SYNTHETIC_KEY_739ab"
    seen = []
    class Proposer:
        def generate(self, *args, **kwargs):
            return SimpleNamespace(text="done", model_ref="fixture:model")
    def factory(*args, credential_bindings, **kwargs):
        seen.append(credential_bindings.value_for("OPENAI_API_KEY"))
        return Proposer()
    monkeypatch.setattr("harness.router_agent.make_authorized_endpoint_proposer", factory)
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=(marker,))
    run_private_agent(operation(tmp_path), {"OPENAI_API_KEY": marker}, tmp_path, writer, None, lambda _: None)
    assert seen == [marker]
    assert marker not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))
