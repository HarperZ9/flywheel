from dataclasses import replace
import json

import pytest

from harness.gateway_grant_route import (
    authorize_gateway_operation,
    gateway_grant_post,
)
from harness.journey_lock import JourneyLockBusy
from harness.gateway_operation import GatewayOperationError
from harness.journey_store import JourneyStore, MutationCommand


NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Bound action", "intake": {},
         "occurred_at": NOW}))


def _prepare(state, operation=None, *, owner=OWNER, clock=lambda: NOW,
             head=None):
    head = head or JourneyStore(state).load(
        OWNER, JOURNEY)["event_head_sha256"]
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY, "expected_event_head": head,
            "client_request_id": "request-1",
            "operation": operation or {"name": "gather"}}
    return gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe",
        json.dumps(body).encode(), owner_ref=owner, state_root=state,
        clock=clock)


def _approval(state, proposal, *, owner=OWNER, clock=lambda: NOW):
    return gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=owner, state_root=state, clock=clock)


def _final(proposal, grant, **changes):
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": proposal["journey_ref"],
            "expected_event_head": proposal["expected_event_head"],
            "client_request_id": proposal["client_request_id"],
            "grant_ref": grant, "name": "gather"}
    body.update(changes)
    return json.dumps(body, separators=(",", ":")).encode()


def test_prepare_approve_and_one_exact_dispatch_survive_new_instances(tmp_path):
    _journey(tmp_path)
    proposal, status = _prepare(tmp_path)
    assert status == 200
    assert set(proposal) == {
        "schema", "proposal_ref", "planned_grant_ref", "action",
        "journey_ref", "expected_event_head", "client_request_id", "tool",
        "operation_sha256", "arguments_sha256", "scopes", "data_refs",
        "credential_refs", "expires_at", "summary"}
    assert proposal["schema"] == "flywheel.gateway-grant-proposal/v1"
    assert proposal["proposal_ref"][4:] == proposal["planned_grant_ref"][4:]
    assert proposal["scopes"] == ["exec", "network", "plugin"]
    approved, approved_status = _approval(tmp_path, proposal)
    assert approved_status == 200
    authorized = authorize_gateway_operation(
        "plugin.probe", _final(proposal, approved["grant_ref"]),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert authorized.action == "plugin.probe"
    assert dict(authorized.operation) == {"name": "gather"}
    with pytest.raises(GatewayOperationError) as reused:
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, approved["grant_ref"]),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert reused.value.code == "APPROVAL_EXPIRED"


@pytest.mark.parametrize("change", [
    {"journey_ref": "jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    {"expected_event_head": "b" * 64},
    {"client_request_id": "request-2"},
    {"name": "forum"},
    {"extra": "field"},
])
def test_every_final_binding_difference_denies_before_consumption(tmp_path, change):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    approval, _ = _approval(tmp_path, proposal)
    with pytest.raises(GatewayOperationError):
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, approval["grant_ref"], **change),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    exact = authorize_gateway_operation(
        "plugin.probe", _final(proposal, approval["grant_ref"]),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert exact.grant_ref == approval["grant_ref"]


@pytest.mark.parametrize("raw", [
    b'{"schema":"flywheel.gateway-operation/v1","schema":"x"}',
    b'[]', b'{"schema":NaN}', b'{"schema":"x","extra":1}',
])
def test_malformed_prepare_is_fixed_and_persists_nothing(tmp_path, raw):
    _journey(tmp_path)
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe", raw,
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert status >= 400 and result["schema"] == (
        "flywheel.evidence-transport-error/v1")
    assert not list((tmp_path / "gateway-grant-proposals").rglob("*.json"))


def test_wrong_owner_and_stale_head_are_non_echoing_and_zero_consume(tmp_path):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    approval, _ = _approval(tmp_path, proposal)
    with pytest.raises(GatewayOperationError) as wrong:
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, approval["grant_ref"]),
            owner_ref=OTHER, state_root=tmp_path, clock=lambda: NOW)
    assert wrong.value.code == "PERMISSION_REQUIRED"
    JourneyStore(tmp_path).append(MutationCommand(
        OWNER, JOURNEY, proposal["expected_event_head"], "append-1",
        "decomposed", {"payload": {}, "occurred_at": NOW}))
    with pytest.raises(GatewayOperationError) as stale:
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, approval["grant_ref"]),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert stale.value.code == "HEAD_CONFLICT"


def test_raw_secret_shape_is_refused_without_echo(tmp_path):
    _journey(tmp_path)
    operation = {"name": "custom", "tool": "run",
                 "arguments": {"api_key": "never-echo"},
                 "credential_refs": []}
    result, status = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.call",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": JourneyStore(tmp_path).load(
                        OWNER, JOURNEY)["event_head_sha256"],
                    "client_request_id": "request-1",
                    "operation": operation}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert status == 422 and result["error"]["code"] == "INVALID_REQUEST"
    assert "never-echo" not in json.dumps(result)


def test_unapproved_absent_and_expired_grants_never_authorize(tmp_path):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    with pytest.raises(GatewayOperationError) as unapproved:
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, proposal["planned_grant_ref"]),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert unapproved.value.code == "PERMISSION_DENIED"
    expired, status = _approval(
        tmp_path, proposal, clock=lambda: "2026-08-15T12:03:00Z")
    assert status == 403 and expired["error"]["code"] == "APPROVAL_EXPIRED"
    with pytest.raises(GatewayOperationError) as absent:
        authorize_gateway_operation(
            "plugin.probe", _final(proposal, "gnt_" + "b" * 32),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert absent.value.code == "PERMISSION_REQUIRED"


def test_canonical_json_order_and_whitespace_do_not_change_binding(tmp_path):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    approval, _ = _approval(tmp_path, proposal)
    body = json.loads(_final(proposal, approval["grant_ref"]))
    raw = json.dumps(dict(reversed(list(body.items()))), indent=3).encode()
    authorized = authorize_gateway_operation(
        "plugin.probe", raw, owner_ref=OWNER, state_root=tmp_path,
        clock=lambda: NOW)
    assert authorized.operation_sha256 == proposal["operation_sha256"]


def test_busy_and_commit_failures_are_fixed_before_proposal(
        tmp_path, monkeypatch):
    _journey(tmp_path)
    head = JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"]
    monkeypatch.setattr(
        "harness.gateway_grant_route.ExclusiveJourneyLock.acquire",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(JourneyLockBusy()))
    busy, busy_status = _prepare(tmp_path, head=head)
    assert busy_status == 503 and busy["error"]["code"] == "STORE_BUSY"
    monkeypatch.undo()
    monkeypatch.setattr("harness.gateway_grant_route._replace",
                        lambda *_args: (_ for _ in ()).throw(OSError()))
    failed, failed_status = _prepare(tmp_path, head=head)
    assert failed_status == 500
    assert failed["error"]["code"] == "STORE_COMMIT_FAILED"
