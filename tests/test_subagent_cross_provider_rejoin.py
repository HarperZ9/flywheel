"""Restart adoption for durable v2 subagent children."""
from __future__ import annotations

import json
import time
from pathlib import Path

from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operations import GatewayOperations
from harness.journey_store import JourneyStore, MutationCommand
from harness.subagent_gateway_bridge import (
    authorize_parent_authority,
    build_bound_spec,
    parent_authority_summary,
)
from harness.subagent_gateway_child import GatewayChildHandle
from harness.subagent_gateway_contract import spec_live_fields
from harness.subagent_store import LIVE_SCHEMA, save_live_state, swarm_dir
from harness.subagents import SwarmRunner

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
NOW = "2026-09-15T12:00:00Z"


def _route(endpoint="stub", model="stub", **extra):
    route = {"endpoint": endpoint, "model": model, "max_steps": 1,
             "max_tokens": 32, "timeout_s": 10}
    route.update(extra)
    return route


def _child(role, route, **extra):
    value = {"role": role, "route": route}
    value.update(extra)
    return value


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


class _CompletedGatewayWorker:
    control_class = "windows_job_v1"

    def resume(self):
        return True

    def wait(self, timeout_s):
        return WorkerOutcome("completed", {"final": "durable child done"})

    def signal_tree(self):
        return True

    def close(self):
        pass


class _CompletedGatewayFactory:
    def create(self, authorized, progress):
        return _CompletedGatewayWorker()


def _await_runner_sealed(runner, swarm_id):
    for _ in range(300):
        snap = runner.snapshot(swarm_id)
        if snap and snap["status"] == "sealed":
            return snap
        time.sleep(0.01)
    raise AssertionError("the adopted swarm never sealed")


def test_v2_adoption_materializes_durable_gateway_result(tmp_path):
    state, run_root = tmp_path / "state", tmp_path / "run"
    state.mkdir(); run_root.mkdir()
    service = GatewayOperations(state, clock=lambda: NOW)
    workspace = tmp_path / "workspace"; workspace.mkdir()
    parent = _parent_envelope(state, workspace, max_steps=2,
                              max_tokens=64, timeout_s=60)
    parent_auth = authorize_parent_authority(
        parent, service, owner_ref=OWNER, workspace_root=workspace)
    parent_summary = parent_authority_summary(parent_auth)
    swarm_id, child_id = "swarm_" + "8" * 12, "sa_" + "9" * 8
    sdir = swarm_dir(run_root, swarm_id); sdir.mkdir(parents=True)
    child_workspace = sdir / ("work_" + child_id); child_workspace.mkdir()
    spec = build_bound_spec(swarm_id=swarm_id, child_id=child_id,
        goal="restart fan-in", child=_child("explore", _route()),
        workspace=child_workspace, created_at=NOW,
        parent_authority=parent_summary, workspace_root=workspace,
        state_root=state)
    (sdir / (child_id + ".spec.json")).write_text(
        json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    GatewayChildHandle(
        spec, parent_auth, service, _CompletedGatewayFactory(), state)
    assert service.wait_terminal(
        OWNER, spec["operation_ref"], 30).state == "completed"
    assert not (child_workspace / "result.json").exists()
    live = {"schema": LIVE_SCHEMA, "swarm_id": swarm_id,
            "created_at": NOW, "timeout_at": time.time() - 1,
            "quorum_policy": "any", "goal": "restart fan-in",
            "endpoint": "mixed", "routing_schema": "flywheel.subagent-routing/v2",
            "state_root": str(state),
            "children": [{"child_id": child_id, "role": "explore",
                "pid": None, "workspace": str(child_workspace),
                "spec_sha256": spec["spec_sha256"],
                **spec_live_fields(spec)}]}
    save_live_state(live, run_root=run_root)

    sealed = _await_runner_sealed(
        SwarmRunner(run_root=run_root, clock=lambda: NOW), swarm_id)
    child = sealed["receipt"]["children"][0]

    assert child["status"] == "completed"
    assert child["reattached"] is True
    assert child["operation_ref"] == spec["operation_ref"]
    assert child["gateway_operation"]["state"] == "completed"
    assert child["route_evidence"]["endpoint"] == "stub"
    assert (child_workspace / "result.json").is_file()
