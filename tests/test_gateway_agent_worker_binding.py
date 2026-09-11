"""Private IPC corruption and actual owned-worker deadline controls."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from harness.gateway_agent_deadline import wait_for_worker
from harness.gateway_operation import AuthorizedOperation, canonicalize_operation
from harness.gateway_operation_process import GatewayAgentProcessFactory, GatewayWorker, WorkerOutcome
from harness.gateway_provider_adapter import freeze_execution_plan


def authorized(tmp_path):
    operation = dict(goal="synthetic execution", endpoint="stub", root=str(tmp_path),
        max_steps=1, max_tokens=64, timeout_s=10, allow_write=False,
        allow_exec=False, stream=True, data_refs=[], credential_refs=[])
    canonical = canonicalize_operation("agent.run", operation)
    base = AuthorizedOperation.for_test(action="agent.run", operation=operation, scopes=("network",))
    return replace(base, operation_sha256=canonical.operation_sha256,
        arguments_sha256=canonical.arguments_sha256, execution_plan=freeze_execution_plan(canonical,
            workspace_root=tmp_path), credential_bindings={})


def captured_payload(tmp_path):
    captured = []
    GatewayAgentProcessFactory(repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
        launcher=lambda spec: captured.append(spec) or object()).create(authorized(tmp_path), lambda event: None)
    return json.loads(captured[0].stdin_bytes)


@pytest.mark.parametrize("change", ["dropped_binding", "model", "budget", "root", "deadline", "boolean_capability"])
def test_private_pipe_rejects_changed_authority_before_router(tmp_path, monkeypatch, change):
    import harness.gateway_operation_process as protocol
    payload = captured_payload(tmp_path)
    if change == "dropped_binding": del payload["agent_binding"]
    if change == "model": payload["agent_binding"]["model"]["model_id"] = "changed"
    if change == "budget": payload["agent_binding"]["budget"]["max_tokens"] = 32768
    if change == "root": payload["agent_binding"]["workspace"]["root"] = str(tmp_path.parent)
    if change == "deadline": payload["deadline"] = time.monotonic() + 100000
    if change == "boolean_capability": payload["agent_binding"]["capabilities"]["allow_exec"] = 0
    monkeypatch.setattr(protocol.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode())))
    with pytest.raises((ValueError, RuntimeError)): protocol._worker_request()


def test_exact_private_pipe_roundtrips_frozen_binding(tmp_path, monkeypatch):
    import harness.gateway_operation_process as protocol
    payload = captured_payload(tmp_path)
    monkeypatch.setattr(protocol.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode())))
    request = protocol._worker_request()
    assert request[0] == payload["operation"] and request[6] == payload["agent_binding"]
    assert request[7] == payload["deadline"]


@pytest.mark.skipif(os.name != "nt", reason="supervised production requires Windows Job Objects")
def test_actual_worker_runs_exact_stub_and_retains_private_binding(tmp_path):
    from harness.gateway_agent_trace import AgentTrace
    from harness.gateway_operation_route import operation_ref_for
    auth = authorized(tmp_path)
    worker = GatewayAgentProcessFactory(repo_root=Path(__file__).resolve().parents[1],
        run_root=tmp_path, state_root=tmp_path).create(auth, lambda event: None)
    try:
        assert worker.resume()
        outcome = worker.wait(15)
        assert outcome is not None and outcome.state == "completed"
        records = AgentTrace(tmp_path, auth.owner_ref, auth.journey_ref,
            operation_ref_for(auth.owner_ref, auth.journey_ref, auth.client_request_id)).read()
        assert records[0]["payload"]["execution_binding"]["model"]["model_id"] == "stub"
        witness = next(r["payload"]["meta"] for r in records if r["kind"] == "ledger"
            and r["payload"]["kind"] == "model_call")
        assert witness["model_observed"] is None and witness["identity_status"] == "unavailable"
    finally: worker.close()


@pytest.mark.skipif(os.name != "nt", reason="owned tree requires Windows Job Objects")
def test_actual_owned_tree_is_stopped_at_aggregate_deadline(tmp_path):
    from harness.cross_harness_process import start_owned_process
    owned = start_owned_process([sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path, stdin_bytes=b"", env={"SYSTEMROOT": os.environ["SYSTEMROOT"]})
    worker = GatewayWorker(owned, lambda event: None, ())
    try:
        assert worker.resume()
        started = time.monotonic()
        result = wait_for_worker(worker, started + .3)
        assert result == WorkerOutcome("failed", {"reason": "OPERATION_DEADLINE_EXCEEDED"})
        assert time.monotonic() - started < 5
        assert owned.wait(0) is not None
    finally: worker.close()


def test_completion_reported_after_deadline_cannot_become_success():
    now = [1.0]
    class Late:
        terminal_observed_at = 3.0
        def wait(self, timeout):
            now[0] = 3.0
            return WorkerOutcome("completed", {})
        def signal_tree(self): return True
    assert wait_for_worker(Late(), 2.0, clock=lambda: now[0]).result == {
        "reason": "OPERATION_DEADLINE_EXCEEDED"}
