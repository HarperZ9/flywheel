from dataclasses import replace
import json

import harness.gateway_operation_process as worker_protocol
from harness.gateway_operation import AuthorizedOperation, thaw_operation
from harness.gateway_operation_process import GatewayAgentProcessFactory
from harness.gateway_provider_adapter import ExecutionPlan
from harness.plan_run_snapshot import freeze_json
from harness.source_context_store import SourceContextStore
from tests.test_source_context_store import CORPUS_ID, OWNER, _selection


def _authorized(ref, plan=None):
    operation = {"goal": "Use the selected context", "endpoint": "local",
        "max_steps": 1, "allow_write": False, "allow_exec": False,
        "stream": True, "root": "workspace", "data_refs": [ref],
        "credential_refs": []}
    base = AuthorizedOperation.for_test(action="agent.run", operation=operation, scopes=("network",))
    return replace(base, owner_ref=OWNER,
        execution_plan=plan or ExecutionPlan("a" * 64, (), ()),
        credential_bindings={})


def _publish(state):
    store = SourceContextStore(state, clock=lambda: "now")
    root_id = store.state_root_identity()
    return store.publish_selection(
        owner_ref=OWNER, state_root_identity=root_id, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection("DECISION-FACT-ALPHA"), selected_at="now")["source_context_ref"]


def _frozen_plan(state, ref):
    frozen = SourceContextStore(state).resolve_worker_payload(OWNER, (ref,))
    return ExecutionPlan("a" * 64, (), (),
        source_context_payload_sha256=frozen["source_payload_sha256"],
        source_context_payload=freeze_json(frozen, max_bytes=1_000_000))


def test_factory_freezes_private_source_bytes_after_grant_for_worker(tmp_path):
    ref = _publish(tmp_path)
    authorized = _authorized(ref, _frozen_plan(tmp_path, ref))
    for path in (tmp_path / "source-context" / "v1" / "owners" / OWNER
                 / "payloads").glob("*.json"):
        path.write_text("{}", encoding="utf-8")
    captured = []
    class Launched:
        def resume(self): return True
        def wait(self, _timeout): return None
        def close(self): pass
    def launcher(spec):
        captured.append(spec)
        return Launched()

    GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
        launcher=launcher).create(authorized, lambda _event: None)

    payload = captured[0].stdin_bytes.decode("utf-8")
    assert "DECISION-FACT-ALPHA" in payload
    assert "source_payload_sha256" in payload
    assert "private/ref" not in payload


def test_worker_sends_exact_selected_text_to_fake_provider_without_reopening(tmp_path, monkeypatch):
    ref = _publish(tmp_path)
    source_payload = SourceContextStore(tmp_path).resolve_worker_payload(OWNER, (ref,))
    operation = thaw_operation(_authorized(ref).operation)
    operation["root"] = str(tmp_path)
    seen = []
    def fake_run(goal, endpoint, **kwargs):
        seen.append(goal)
        return {"final": "ok"}
    monkeypatch.setattr("harness.router_agent.run_router_agent", fake_run)

    result = worker_protocol._run_agent(operation, {}, tmp_path, tmp_path, source_payload)

    assert result["final"] == "ok"
    assert "DECISION-FACT-ALPHA" in seen[0]
    assert seen[0].count("DECISION-FACT-ALPHA") == 1
    assert "truth" in seen[0]


def test_missing_frozen_source_payload_returns_typed_failure_without_launch(tmp_path):
    ref = _publish(tmp_path)
    launched = []

    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
        launcher=lambda spec: launched.append(spec)).create(
            _authorized(ref), lambda _event: None)
    outcome = worker.wait(0)

    assert launched == []
    assert outcome.state == "failed"
    assert outcome.result["reason"] == "SOURCE_CONTEXT_FAILED"


def test_missing_frozen_source_payload_with_no_state_root_fails_before_launch(
        tmp_path):
    ref = _publish(tmp_path)
    launched = []
    class Launched:
        def resume(self): return True
        def wait(self, _timeout): return None
        def close(self): pass

    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path,
        launcher=lambda spec: (launched.append(spec), Launched())[1]).create(
            _authorized(ref), lambda _event: None)
    outcome = worker.wait(0)

    assert launched == []
    assert outcome.state == "failed"
    assert outcome.result["reason"] == "SOURCE_CONTEXT_FAILED"


def test_frozen_source_payload_with_no_state_root_is_sent_to_worker(tmp_path):
    ref = _publish(tmp_path)
    captured = []
    class Launched:
        def resume(self): return True
        def wait(self, _timeout): return None
        def close(self): pass

    GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path,
        launcher=lambda spec: (captured.append(spec), Launched())[1]).create(
            _authorized(ref, _frozen_plan(tmp_path, ref)), lambda _event: None)

    payload = json.loads(captured[0].stdin_bytes)
    source = payload["source_context"]
    assert source["contexts"][0]["rows"][0]["text"] == "DECISION-FACT-ALPHA"
    assert source["source_payload_sha256"] == source["source_payload_sha256"].lower()
