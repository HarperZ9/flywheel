import hashlib

import pytest

from inspect_http_support import InspectGateway, projected_inspect_log


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    harness = InspectGateway(tmp_path, monkeypatch).start()
    try:
        yield harness
    finally:
        harness.close()


def _approve_upload(gateway, raw, request_id):
    status, proposal = gateway.prepare_import(raw, request_id)
    assert status == 200
    status, approval = gateway.approve(proposal)
    assert status == 200
    return proposal, approval["grant_ref"]


def _by_pointer(report):
    return {item["json_pointer"]: item["source_value"]
            for item in report["source_pointers"]}


def test_loopback_upload_readback_restart_and_tamper_controls(gateway):
    raw = projected_inspect_log()
    source_sha = hashlib.sha256(raw).hexdigest()

    proposal, grant_ref = _approve_upload(gateway, raw, "inspect-http-ok")
    status, uploaded = gateway.upload(raw, proposal, grant_ref)

    assert status == 200
    assert uploaded["schema"] == "flywheel.inspect-import-result/v1"
    assert uploaded["source"]["sha256"] == source_sha
    assert uploaded["source"]["byte_length"] == len(raw)
    assert uploaded["data_ref"] == f"data_inspect.source:{source_sha[:32]}"
    report = uploaded["report"]
    assert report["reported_status"] == "success"
    assert report["assessment"] == "reported"
    assert report["semantic_verification"] == "UNVERIFIABLE"
    pointers = _by_pointer(report)
    assert pointers["/status"] == "success"
    assert pointers["/eval/task"] == "flywheel_inspect_import"
    assert pointers["/samples/0/scores/match/value"] == "C"
    assert pointers["/samples/1/scores/match/value"] == "I"

    eid = uploaded["stored"]["eid"]
    gateway.restart()
    status, detail = gateway.get_json(f"/api/import/inspect/{eid}")
    assert status == 200
    assert detail == uploaded
    status, listed = gateway.get_json("/api/import/inspect?limit=1")
    assert status == 200
    assert listed["items"][0]["eid"] == eid
    assert listed["items"][0]["reported_status"] == "success"
    assert "report" not in listed["items"][0]

    status, missing = gateway.get_json("/api/import/inspect", bearer=False)
    assert status == 401
    assert missing["error"]["code"] == "AUTH_REQUIRED"

    gateway.tamper_source_hash(eid)
    status, tampered = gateway.get_json(f"/api/import/inspect/{eid}")
    assert status == 409
    assert tampered["error"]["code"] == "STORE_TAMPERED"


def test_preapproval_rejection_or_changed_source_does_not_create_store(gateway):
    raw = projected_inspect_log()
    status, rejected = gateway.prepare_import(raw, "inspect-http-reject")
    assert status == 200
    status, rejection = gateway.reject(rejected)
    assert status == 200
    assert rejection["proposal_state"] == "rejected"

    status, denied = gateway.upload(raw, rejected, rejected["planned_grant_ref"])
    assert status == 403
    assert denied["error"]["code"] == "PERMISSION_DENIED"
    assert not gateway.inspect_store().exists()
    assert not (gateway.ambient_home / "store.db").exists()

    proposal, grant_ref = _approve_upload(gateway, raw, "inspect-http-changed")
    changed = raw.replace(b'"success"', b'"started"', 1)
    status, changed_denied = gateway.upload(changed, proposal, grant_ref)
    assert status == 403
    assert changed_denied["error"]["code"] == "PERMISSION_DENIED"
    assert not gateway.inspect_store().exists()
    assert not (gateway.ambient_home / "store.db").exists()


def test_preapproval_reject_does_not_claim_to_withdraw_approved_grant(gateway):
    raw = projected_inspect_log()
    proposal, _grant_ref = _approve_upload(
        gateway, raw, "inspect-http-no-withdraw")

    gateway.restart()
    status, refused = gateway.reject(proposal)
    assert status == 409
    assert refused["error"]["code"] == "INVALID_TRANSITION"

    status, readback = gateway.read_proposal(proposal)
    assert status == 200
    assert readback["proposal_state"] == "approved"
    assert readback["derived_state"] == "approved_waiting_dispatch"
    assert not gateway.inspect_store().exists()
    assert not (gateway.ambient_home / "store.db").exists()
