"""Cross-provider subagent routing controls."""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from harness.credential_handles import CredentialHandleStore
from harness.gateway_grant_route import gateway_grant_post, authorize_gateway_operation
from harness.gateway_operation_process import GatewayAgentProcessFactory
from harness.gateway_operations import GatewayOperations
from harness.journey_store import JourneyStore, MutationCommand
from harness.providers import ProviderSpec, REGISTRY
from harness.subagent_gateway_bridge import SPAWN_SCHEMA_V2
from harness.subagents import SwarmRunner
from harness.subagents_route import handle_subagents_get, handle_subagents_post

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
NOW = "2026-09-15T12:00:00Z"
SECRET = "SYNTHETIC_CHILD_KEY_9a55"


def _route(endpoint="stub", model="stub", **extra):
    route = {"endpoint": endpoint, "model": model, "max_steps": 1,
             "max_tokens": 32, "timeout_s": 10}
    route.update(extra)
    return route


def _child(role, route, **extra):
    value = {"role": role, "route": route}
    value.update(extra)
    return value


def _await_sealed(run_root, swarm_id):
    for _ in range(800):
        snap, status = handle_subagents_get(
            "/api/subagents/swarm", "id=" + swarm_id, run_root=run_root)
        if status == 200 and snap["status"] == "sealed":
            return snap
        time.sleep(0.01)
    raise AssertionError("the swarm never sealed")


@contextmanager
def _openai_provider_stub():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append((self.path, dict(self.headers), raw))
            body = json.dumps({"model": "synthetic-model",
                "choices": [{"message": {"content": "Synthetic provider done."}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                          "total_tokens": 3}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def _install_synthetic_openai(monkeypatch, shim_root: Path, base_url: str):
    spec = ProviderSpec("synthetic-openai", base_url, "SYNTHETIC_API_KEY",
                        "synthetic-model", local=True)
    monkeypatch.setitem(REGISTRY, "synthetic-openai", spec)
    (shim_root / "sitecustomize.py").write_text(
        "from harness.providers import ProviderSpec, REGISTRY\n"
        f"REGISTRY['synthetic-openai'] = ProviderSpec('synthetic-openai', {base_url!r}, 'SYNTHETIC_API_KEY', 'synthetic-model', local=True)\n",
        encoding="utf-8")
    prior = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(shim_root) + (
        os.pathsep + prior if prior else ""))


def _service(tmp_path):
    state, run_root = tmp_path / "state", tmp_path / "run"
    state.mkdir(); run_root.mkdir()
    service = GatewayOperations(state, clock=lambda: NOW)
    factory = GatewayAgentProcessFactory(
        repo_root=Path(__file__).resolve().parents[1],
        run_root=run_root, state_root=state)
    return state, run_root, service, factory


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "fixture", "intake": {},
         "occurred_at": NOW})).event_head_sha256


def _parent_envelope(state, workspace, *, max_steps=4, max_tokens=128,
                     timeout_s=60):
    head = _journey(state)
    operation = {"goal": "delegate bounded children", "endpoint": "stub",
        "model": "stub", "root": str(workspace), "max_steps": max_steps,
        "max_tokens": max_tokens, "timeout_s": timeout_s,
        "allow_write": False, "allow_exec": False, "stream": False,
        "data_refs": [], "credential_refs": []}
    base = {"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "parent-swarm", "operation": operation}
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run", json.dumps(base).encode(),
        owner_ref=OWNER, state_root=state, workspace_root=workspace,
        clock=lambda: NOW)
    assert status == 200, proposal
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, approval
    return {**{k: v for k, v in base.items() if k != "operation"},
            **operation, "grant_ref": approval["grant_ref"]}


def _body(parent, children, **extra):
    body = {"schema": SPAWN_SCHEMA_V2, "goal": "compare child routes",
            "parent_authority": parent, "children": children,
            "quorum_policy": "all", "timeout_s": 30.0}
    body.update(extra)
    return body


def _post(body, *, run_root, service, factory, workspace):
    return handle_subagents_post(
        "/api/subagents/spawn", body, run_root=run_root, clock=lambda: NOW,
        owner_ref=OWNER, state_root=service.state_root,
        operation_service=service, process_factory=factory,
        workspace_root=workspace)


def test_v2_spawn_refuses_string_or_unwired_parent_authority(tmp_path):
    state, run_root, service, factory = _service(tmp_path)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    child = _child("explore", _route())
    response, status = _post(_body("op_" + "c" * 32, [child]),
        run_root=run_root, service=service, factory=factory, workspace=workspace)
    assert status == 422
    assert "parent authority" in response["error"]["message"]

    response, status = handle_subagents_post(
        "/api/subagents/spawn", _body({}, [child]), run_root=run_root,
        clock=lambda: NOW)
    assert status == 422
    assert "gateway operation service" in response["error"]["message"]


def test_aggregate_budget_overflow_is_rejected_before_parent_grant_burn(tmp_path):
    state, run_root, service, factory = _service(tmp_path)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    parent = _parent_envelope(state, workspace, max_steps=1,
                              max_tokens=64, timeout_s=60)
    children = [_child("explore", _route(max_tokens=32)),
                _child("review", _route(max_tokens=32))]
    response, status = _post(_body(parent, children), run_root=run_root,
        service=service, factory=factory, workspace=workspace)
    assert status == 422
    assert "aggregate child steps" in response["error"]["message"]

    raw = json.dumps(parent).encode()
    authorized = authorize_gateway_operation(
        "agent.run", raw, owner_ref=OWNER, state_root=state,
        workspace_root=workspace, clock=lambda: NOW)
    assert authorized.grant_ref == parent["grant_ref"]



def test_invalid_child_credentials_do_not_consume_parent_grant(
        tmp_path, monkeypatch):
    state, run_root, service, factory = _service(tmp_path)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    parent = _parent_envelope(state, workspace, max_steps=2,
                              max_tokens=64, timeout_s=60)
    _install_synthetic_openai(monkeypatch, tmp_path, "http://127.0.0.1:1/v1")
    child = _child("review", _route("synthetic-openai", "synthetic-model",
                                     credential_refs=[]))

    response, status = _post(_body(parent, [child]), run_root=run_root,
        service=service, factory=factory, workspace=workspace)

    assert status == 422
    assert "PERMISSION_REQUIRED" in response["error"]["message"]
    authorized = authorize_gateway_operation(
        "agent.run", json.dumps(parent).encode(), owner_ref=OWNER,
        state_root=state, workspace_root=workspace, clock=lambda: NOW)
    assert authorized.grant_ref == parent["grant_ref"]

def test_direct_runner_rejects_caller_shaped_v2_parent_authority(tmp_path):
    runner = SwarmRunner(run_root=tmp_path, clock=lambda: NOW)
    with pytest.raises(ValueError, match="authorized gateway operation"):
        runner.spawn(goal="fixture", children=[_child("explore", _route())],
                     parent_authority={"schema": "caller-authored"})


def test_v2_worker_refuses_direct_spec_execution(tmp_path):
    import harness.subagent_worker as worker
    spec = {"schema": "flywheel.subagent-spec/v2",
            "workspace": str(tmp_path), "spec_sha256": "x"}
    assert worker.execute(spec) == worker.EXIT_FAILED
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["status"] == "failed"
    assert result["error"] == "GATEWAY_CHILD_OPERATION_REQUIRED"

@pytest.mark.skipif(os.name != "nt", reason="gateway worker requires Windows")
def test_gateway_owned_v2_children_use_credentials_and_lifecycle(
        tmp_path, monkeypatch):
    state, run_root, service, factory = _service(tmp_path)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    parent = _parent_envelope(state, workspace, max_steps=3,
                              max_tokens=128, timeout_s=90)
    cred = CredentialHandleStore(
        state, keychain_get=lambda name: SECRET).bind(
            OWNER, "SYNTHETIC_API_KEY")
    monkeypatch.setattr("harness.keychain.resolve_credential",
                        lambda name: SECRET if name == "SYNTHETIC_API_KEY" else "")
    with _openai_provider_stub() as (base_url, requests):
        _install_synthetic_openai(monkeypatch, tmp_path, base_url)
        children = [
            _child("explore", _route("stub", "stub")),
            _child("review", _route("synthetic-openai", "synthetic-model",
                max_tokens=32, timeout_s=20, credential_refs=[cred.credential_ref])),
        ]
        response, status = _post(_body(parent, children), run_root=run_root,
            service=service, factory=factory, workspace=workspace)
        assert status == 200, response
        receipt = _await_sealed(run_root, response["swarm_id"])["receipt"]

    assert receipt["routing_schema"] == "flywheel.subagent-routing/v2"
    assert receipt["endpoint"] == "mixed"
    by_endpoint = {c["route_evidence"]["endpoint"]: c
                   for c in receipt["children"]}
    assert set(by_endpoint) == {"stub", "synthetic-openai"}
    assert by_endpoint["synthetic-openai"]["route_evidence"]["adapter"] == "openai"
    assert by_endpoint["synthetic-openai"]["usage"] == {
        "prompt": 1, "completion": 2, "total": 3}
    assert requests and requests[0][1]["Authorization"] == "Bearer " + SECRET
    refs = service.operation_refs(OWNER)
    child_refs = {c["gateway_operation"]["operation_ref"]
                  for c in receipt["children"]}
    assert child_refs <= refs and len(child_refs) == 2
    events = service._journey(OWNER)._events(JOURNEY)
    types = [event["event_type"] for event in events]
    reservations = [event for event in events if event["event_type"] == "record_receipt"
                    and event["payload"].get("schema") == "flywheel.subagent-budget-reservation/v1"]
    assert len(reservations) == 1
    for kind in ("operation_queued", "operation_started",
                 "operation_completed"):
        assert types.count(kind) >= 2
