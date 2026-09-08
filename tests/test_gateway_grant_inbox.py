import json
import threading

from gateway_grant_relay_source_fixture import relay_source_runtime  # noqa: F401

from harness.gateway_grant_route import (
    authorize_gateway_operation,
    gateway_grant_post,
)
from harness.gateway_operation_route import operation_ref_for
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-09-07T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER_JOURNEY = "jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _journey(root, owner=OWNER, journey=JOURNEY):
    return JourneyStore(root).create(MutationCommand(
        owner, journey, None, f"create-{journey[-4:]}", "intake",
        {"legacy_label": None, "goal": "approve mobile",
         "intake": {}, "occurred_at": NOW}))


def _operation(**changes):
    value = {"name": "relay", "tool": "relay.run",
             "arguments": {"goal": "write summary", "limit": 2},
             "data_refs": ["data_mobile"], "credential_refs": []}
    value.update(changes)
    return value


def _prepare(root, *, owner=OWNER, journey=JOURNEY, request="request-1",
             operation=None, clock=lambda: NOW):
    head = JourneyStore(root).load(owner, journey)["event_head_sha256"]
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey, "expected_event_head": head,
            "client_request_id": request,
            "operation": operation or _operation()}
    return gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.call",
        json.dumps(body).encode(), owner_ref=owner, state_root=root,
        clock=clock)


def _post(root, route, body, *, owner=OWNER, clock=lambda: NOW):
    return gateway_grant_post(
        f"/api/gateway-grants/{route}", json.dumps(body).encode(),
        owner_ref=owner, state_root=root, clock=clock)


def _read(root, proposal, *, owner=OWNER, clock=lambda: NOW):
    return _post(root, "read", {
        "schema": "flywheel.gateway-grant-read-request/v1",
        "proposal_ref": proposal["proposal_ref"]}, owner=owner, clock=clock)


def _review(root, proposal, *, owner=OWNER):
    value, status = _read(root, proposal, owner=owner)
    assert status == 200, value
    assert value["review_available"] is True
    return value["review"]


def _approve_reviewed(root, proposal, review, *, owner=OWNER,
                      clock=lambda: NOW):
    return _post(root, "approve-reviewed-once", {
        "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
        "proposal_ref": proposal["proposal_ref"],
        "review_sha256": review["review_sha256"]}, owner=owner,
        clock=clock)


def _approve_legacy(root, proposal, *, owner=OWNER, clock=lambda: NOW):
    return _post(root, "approve-once",
                 {"proposal_ref": proposal["proposal_ref"]},
                 owner=owner, clock=clock)


def _reject(root, item, *, owner=OWNER, clock=lambda: NOW):
    return _post(root, "reject", {
        "schema": "flywheel.gateway-grant-reject-request/v1",
        "proposal_ref": item["proposal_ref"],
        "expected_record_sha256": item["record_sha256"]},
        owner=owner, clock=clock)


def _final(proposal, grant, **changes):
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": proposal["journey_ref"],
            "expected_event_head": proposal["expected_event_head"],
            "client_request_id": proposal["client_request_id"],
            "grant_ref": grant, **_operation()}
    body.update(changes)
    return json.dumps(body, separators=(",", ":")).encode()


def test_missing_owner_mutations_are_permission_denied(tmp_path):
    proposal = {"proposal_ref": "prp_" + "a" * 32}
    review = {"review_sha256": "0" * 64}

    value, status = _approve_reviewed(tmp_path, proposal, review)
    assert status == 403
    assert value["error"]["code"] == "PERMISSION_REQUIRED"

    item = {**proposal, "record_sha256": "1" * 64}
    value, status = _reject(tmp_path, item)
    assert status == 403
    assert value["error"]["code"] == "PERMISSION_REQUIRED"


def test_capabilities_list_and_read_exact_review_are_owner_scoped(tmp_path):
    _journey(tmp_path)
    _journey(tmp_path, owner=OTHER, journey=OTHER_JOURNEY)
    proposal, status = _prepare(tmp_path)
    assert status == 200
    other, other_status = _prepare(
        tmp_path, owner=OTHER, journey=OTHER_JOURNEY, request="other-1")
    assert other_status == 200

    caps, status = _post(tmp_path, "capabilities", {
        "schema": "flywheel.gateway-grant-capabilities-request/v1"})
    assert status == 200
    assert caps["reviewed_approval"] is True
    assert caps["durable_reject"] is True

    listed, status = _post(tmp_path, "list", {
        "schema": "flywheel.gateway-grant-list-request/v1",
        "state": "pending", "limit": 25, "cursor": None})
    assert status == 200
    assert [row["proposal_ref"] for row in listed["items"]] == [
        proposal["proposal_ref"]]
    row = listed["items"][0]
    assert row["operation_ref"] == operation_ref_for(
        OWNER, JOURNEY, "request-1")
    assert row["review_available"] is True
    assert "operation" not in row

    read, status = _read(tmp_path, proposal)
    assert status == 200
    review = read["review"]
    assert review["operation"] == _operation()
    assert review["credential_refs"] == []
    assert review["review_sha256"] == row["review_sha256"]
    assert "write summary" in json.dumps(review)

    other_list, status = _post(tmp_path, "list", {
        "schema": "flywheel.gateway-grant-list-request/v1",
        "state": "pending", "limit": 25, "cursor": None}, owner=OTHER)
    assert status == 200
    assert [row["proposal_ref"] for row in other_list["items"]] == [
        other["proposal_ref"]]


def test_reviewed_approval_requires_review_hash_and_legacy_stays_compatible(
        tmp_path):
    _journey(tmp_path)
    legacy, _ = _prepare(tmp_path, request="legacy")
    approved, status = _approve_legacy(tmp_path, legacy)
    assert status == 200
    assert approved["grant_ref"] == legacy["planned_grant_ref"]

    proposal, _ = _prepare(tmp_path, request="reviewed")
    wrong, status = _post(tmp_path, "approve-reviewed-once", {
        "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
        "proposal_ref": proposal["proposal_ref"],
        "review_sha256": "0" * 64})
    assert status == 403
    assert wrong["error"]["code"] == "PERMISSION_DENIED"

    review = _review(tmp_path, proposal)
    reviewed, status = _approve_reviewed(tmp_path, proposal, review)
    assert status == 200
    assert reviewed["grant_ref"] == proposal["planned_grant_ref"]
    authorized = authorize_gateway_operation(
        "plugin.call", _final(proposal, reviewed["grant_ref"]),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert authorized.grant_ref == reviewed["grant_ref"]


def test_review_unavailable_blocks_reviewed_approval(tmp_path):
    _journey(tmp_path)
    proposal, status = _prepare(tmp_path, operation=_operation(
        arguments={"payload": "x" * 40000}))
    assert status == 200
    read, status = _read(tmp_path, proposal)
    assert status == 200
    assert read["review_available"] is False
    assert read["derived_state"] == "review_unavailable"
    denied, status = _post(tmp_path, "approve-reviewed-once", {
        "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
        "proposal_ref": proposal["proposal_ref"],
        "review_sha256": "0" * 64})
    assert status == 403
    assert denied["error"]["code"] == "PERMISSION_DENIED"


def test_reject_is_durable_and_never_consumes_or_dispatches(tmp_path):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    listed, _ = _post(tmp_path, "list", {
        "schema": "flywheel.gateway-grant-list-request/v1",
        "state": "pending", "limit": 25, "cursor": None})
    rejected, status = _reject(tmp_path, listed["items"][0])
    assert status == 200
    assert rejected["proposal_state"] == "rejected"

    read, status = _read(tmp_path, proposal)
    assert status == 200
    assert read["proposal_state"] == "rejected"
    legacy, status = _approve_legacy(tmp_path, proposal)
    assert status == 403
    assert legacy["error"]["code"] == "PERMISSION_DENIED"
    reviewed, status = _approve_reviewed(
        tmp_path, proposal, {"review_sha256": "0" * 64})
    assert status == 403
    assert reviewed["error"]["code"] == "PERMISSION_DENIED"

    try:
        authorize_gateway_operation(
            "plugin.call", _final(proposal, proposal["planned_grant_ref"]),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    except Exception as exc:
        assert getattr(exc, "code", None) == "PERMISSION_DENIED"
    else:
        raise AssertionError("rejected proposal authorized")


def test_approve_reject_race_reports_one_winner(tmp_path):
    _journey(tmp_path)
    proposal, _ = _prepare(tmp_path)
    read, _ = _read(tmp_path, proposal)
    item = {"proposal_ref": proposal["proposal_ref"],
            "record_sha256": read["record_sha256"]}
    review = read["review"]
    barrier = threading.Barrier(3)
    outcomes = []

    def approve():
        barrier.wait()
        outcomes.append(("approve", _approve_reviewed(
            tmp_path, proposal, review)))

    def reject():
        barrier.wait()
        outcomes.append(("reject", _reject(tmp_path, item)))

    threads = [threading.Thread(target=approve), threading.Thread(target=reject)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    statuses = {name: result[1] for name, result in outcomes}
    assert list(statuses.values()).count(200) == 1
    assert sorted(status for status in statuses.values() if status != 200
                  ) in ([403], [409])
    final, status = _read(tmp_path, proposal)
    assert status == 200
    assert final["proposal_state"] in {"approved", "rejected"}
