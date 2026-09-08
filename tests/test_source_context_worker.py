from dataclasses import replace

import harness.gateway_operation_process as worker_protocol
from harness.gateway_operation import AuthorizedOperation, thaw_operation
from harness.gateway_operation_process import GatewayAgentProcessFactory
from harness.gateway_provider_adapter import ExecutionPlan
from harness.source_context_store import SourceContextStore

OWNER = "owner_" + "a" * 32
ROOT_ID = {"platform": "windows", "volume_serial": 1, "file_index": 2}
CORPUS_ID = {"platform": "windows", "volume_serial": 1, "file_index": 3}


def _authorized(ref):
    operation = {"goal": "Use the selected context", "endpoint": "local",
        "max_steps": 1, "allow_write": False, "allow_exec": False,
        "stream": True, "root": "workspace", "data_refs": [ref],
        "credential_refs": []}
    base = AuthorizedOperation.for_test(action="agent.run", operation=operation, scopes=("network",))
    return replace(base, owner_ref=OWNER, execution_plan=ExecutionPlan("a" * 64, (), ()), credential_bindings={})


def _publish(state):
    payload = {"schema": "gather.readable-context/v1", "corpus_digest": "c" * 64,
        "selection_digest": "d" * 64, "selection_count": 1,
        "selections": [{"row_ref": "row_abc", "kind": "document", "id": "alpha",
            "title": "Private", "source": "docs", "ref": "private/ref",
            "method": "file-read", "sha256": "e" * 64,
            "verified_sha256": "f" * 64, "derived_from": [],
            "full_text_chars": 40, "body_bytes_read": 40,
            "range": {"start": 0, "end": 19},
            "text": "DECISION-FACT-ALPHA", "omissions": []}],
        "omissions": [], "does_not_prove": ["truth"],
        "verified": True, "verified_scope": "selected_rows"}
    return SourceContextStore(state, clock=lambda: "now").publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=payload, selected_at="now")["source_context_ref"]


def test_factory_freezes_private_source_bytes_after_grant_for_worker(tmp_path):
    ref = _publish(tmp_path)
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
        launcher=launcher).create(_authorized(ref), lambda _event: None)

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


def test_post_grant_source_corruption_returns_typed_failure_without_launch(tmp_path):
    ref = _publish(tmp_path)
    for path in (tmp_path / "source-context" / "v1" / "owners" / OWNER
                 / "payloads").glob("*.json"):
        path.write_text("{}", encoding="utf-8")
    launched = []

    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
        launcher=lambda spec: launched.append(spec)).create(
            _authorized(ref), lambda _event: None)
    outcome = worker.wait(0)

    assert launched == []
    assert outcome.state == "failed"
    assert outcome.result["reason"] == "SOURCE_CONTEXT_FAILED"
