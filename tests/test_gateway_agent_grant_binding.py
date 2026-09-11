"""Prepare/consume/replay controls over frozen concrete agent authority."""
from dataclasses import replace
import json

import pytest

from harness.gateway_grant_route import gateway_grant_post, authorize_gateway_operation
from harness.gateway_operation import GatewayOperationError
from harness.journey_store import JourneyStore, MutationCommand
from harness.plan_run_snapshot import thaw_json

OWNER, JOURNEY = "owner_" + "a" * 32, "jrn_" + "b" * 32
NOW = "2026-09-10T20:00:00Z"


def prepared(tmp_path, **changes):
    state, workspace = tmp_path / "state", tmp_path / "workspace"
    state.mkdir(); workspace.mkdir()
    head = JourneyStore(state).create(MutationCommand(OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "fixture", "intake": {}, "occurred_at": NOW})).event_head_sha256
    operation = dict(goal="fixture", endpoint="ollama", max_steps=2,
        max_tokens=321, timeout_s=20, allow_exec=False, allow_write=False,
        stream=True, data_refs=[], credential_refs=[], **changes)
    base = dict(schema="flywheel.gateway-operation/v1", journey_ref=JOURNEY,
        expected_event_head=head, client_request_id="fixture")
    proposal, status = gateway_grant_post("/api/gateway-grants/prepare/agent.run",
        json.dumps(dict(base, operation=operation)).encode(), owner_ref=OWNER,
        state_root=state, workspace_root=workspace, clock=lambda: NOW)
    assert status == 200, proposal
    return state, workspace, proposal, dict(base, **operation)


def approve(state, proposal, envelope):
    approval, status = gateway_grant_post("/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(), owner_ref=OWNER,
        state_root=state, clock=lambda: NOW)
    assert status == 200, approval
    return json.dumps(dict(envelope, grant_ref=approval["grant_ref"])).encode()


def test_grant_review_shows_frozen_default_and_actual_workspace_not_child_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    state, workspace, proposal, envelope = prepared(tmp_path)
    review = proposal["summary"]["agent_execution"]
    assert review["model"]["requested_model_reference"] is None
    assert review["model"]["selection"] == "frozen_default"
    assert review["root"] == str(workspace.resolve())
    assert review["budget"] == {"max_steps": 2, "max_tokens": 321, "timeout_s": 20}
    raw = approve(state, proposal, envelope)
    authorized = authorize_gateway_operation("agent.run", raw, owner_ref=OWNER,
        state_root=state, workspace_root=workspace, clock=lambda: NOW)
    assert authorized.execution_plan.agent_binding.sha256 == review["binding_sha256"]
    assert thaw_json(authorized.execution_plan.agent_binding)["workspace"]["root"] == review["root"]


@pytest.mark.parametrize("drift", ["model_default", "url", "root", "policy"])
def test_parent_authority_drift_denies_before_consuming_grant(tmp_path, monkeypatch, drift):
    from harness.providers import REGISTRY
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    state, workspace, proposal, envelope = prepared(tmp_path)
    raw = approve(state, proposal, envelope)
    original = REGISTRY["ollama"]
    with monkeypatch.context() as patch:
        if drift == "model_default": patch.setitem(REGISTRY, "ollama", replace(original, default_model="changed"))
        if drift == "url": patch.setitem(REGISTRY, "ollama", replace(original, base_url="http://127.0.0.1:1/v1"))
        if drift == "policy": patch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(workspace))
        default = state if drift == "root" else workspace
        with pytest.raises(GatewayOperationError, match="AGENT_BINDING_DRIFT"):
            authorize_gateway_operation("agent.run", raw, owner_ref=OWNER,
                state_root=state, workspace_root=default, clock=lambda: NOW)
    assert authorize_gateway_operation("agent.run", raw, owner_ref=OWNER,
        state_root=state, workspace_root=workspace, clock=lambda: NOW).grant_ref


def test_old_approved_agent_proposal_is_readable_but_requires_reprepare(tmp_path, monkeypatch):
    from harness.gateway_grant_route import _digest, _validate_record
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    state, workspace, proposal, envelope = prepared(tmp_path)
    raw = approve(state, proposal, envelope)
    paths = list((state / "gateway-grant-proposals" / OWNER).glob("*.json"))
    path = next(p for p in paths if json.loads(p.read_text()).get("proposal_ref") == proposal["proposal_ref"])
    record = json.loads(path.read_text()); del record["agent_binding"]
    record["record_sha256"] = _digest(record); path.write_text(json.dumps(record))
    assert _validate_record(record, OWNER) == record
    with pytest.raises(GatewayOperationError, match="AGENT_REPREPARE_REQUIRED"):
        authorize_gateway_operation("agent.run", raw, owner_ref=OWNER,
            state_root=state, workspace_root=workspace, clock=lambda: NOW)


def test_terminal_replay_does_not_re_resolve_new_configuration(tmp_path, monkeypatch):
    from gateway_route_fixtures import _setup, Factory, Process, OWNER as fixture_owner
    from harness.gateway_operation_process import WorkerOutcome
    from harness.gateway_operation_route import route_gateway_operation
    service, raw = _setup(tmp_path, stream=False)
    factory = Factory(Process(WorkerOutcome("completed", {"final": "fixture"})))
    def dispatch():
        return route_gateway_operation("POST", "/api/agent", raw=raw, owner_ref=fixture_owner,
            service=service, process_factory=factory, content_type="application/json")
    first = dispatch(); assert first.status == 200
    monkeypatch.setattr("harness.gateway_provider_adapter.freeze_execution_plan",
        lambda *a, **kw: pytest.fail("replay re-resolved authority"))
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(tmp_path / "different"))
    second = dispatch()
    assert second.body == first.body and factory.calls == 1


@pytest.mark.parametrize("mode", ["explicit", "default"])
def test_native_review_fixture_is_backend_derived_and_hash_bound(mode):
    from pathlib import Path
    from harness.gateway_agent_grant import review_binding
    from harness.gateway_operation import canonicalize_operation
    from harness.evidence_json import canonical_sha256
    folder = Path(__file__).parent / "fixtures" / "native_agent_binding"
    binding = json.loads((folder / f"{mode}-binding.json").read_text())
    operation = json.loads((folder / f"{mode}-operation.json").read_text())
    review = json.loads((folder / f"{mode}-review.json").read_text())
    assert review_binding({"agent_binding": binding}) == review
    assert review["binding_sha256"] == canonical_sha256(binding)
    assert binding["operation_sha256"] == canonicalize_operation("agent.run", operation).operation_sha256
    assert review_binding({}) == json.loads((folder / "reprepare-review.json").read_text())
