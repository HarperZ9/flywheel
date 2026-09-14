import base64
import hashlib
import json

import pytest

from harness.inspect_unit_contract_route import (
    REQUEST_SCHEMA as UNIT_CONTRACT_REQUEST_SCHEMA,
    UNIT_CONTRACT_UPLOAD_MEDIA_TYPE,
)
from inspect_http_support import InspectGateway, projected_inspect_log
from tests.test_inspect_evidence_cli import _unit_contract_for


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


def _unit_log():
    return {
        "version": 2,
        "status": "success",
        "eval": {"task": "unit-contract", "model": "mockllm/model"},
        "results": {"total_samples": 1, "completed_samples": 1,
                    "scores": [{"name": "match", "scorer": "match",
                                "scored_samples": 1, "unscored_samples": 0}]},
        "samples": [{"id": "one", "epoch": 1,
                     "output": {"completion": "def test_one():\n    assert True"},
                     "scores": {"match": {"value": "I"}}}],
    }


def _sidecar_body(raw, unit):
    return json.dumps({
        "schema": UNIT_CONTRACT_REQUEST_SCHEMA,
        "filename": "single-success.fixture.json",
        "inspect_sha256": hashlib.sha256(raw).hexdigest(),
        "inspect_byte_length": len(raw),
        "inspect_json_base64": base64.b64encode(raw).decode("ascii"),
        "unit_contract_json_base64": base64.b64encode(unit).decode("ascii"),
    }, separators=(",", ":")).encode("utf-8")


def _sidecar_headers(proposal, grant_ref, content_type=UNIT_CONTRACT_UPLOAD_MEDIA_TYPE):
    return {
        "Content-Type": content_type,
        "X-Flywheel-Journey-Ref": proposal["journey_ref"],
        "X-Flywheel-Expected-Event-Head": proposal["expected_event_head"],
        "X-Flywheel-Client-Request-Id": proposal["client_request_id"],
        "X-Flywheel-Grant-Ref": grant_ref,
    }


def _unit_contract_upload(gateway):
    log = _unit_log()
    raw = json.dumps(log, separators=(",", ":")).encode("utf-8")
    unit = json.dumps(_unit_contract_for(log), separators=(",", ":")).encode("utf-8")
    proposal, grant_ref = _approve_upload(gateway, raw, "inspect-http-unit")
    return _sidecar_body(raw, unit), proposal, grant_ref


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


def test_loopback_sidecar_upload_stores_unit_contract_report_and_readback(gateway):
    body, proposal, grant_ref = _unit_contract_upload(gateway)

    status, uploaded = gateway.request(
        "POST", "/api/import/inspect", body,
        _sidecar_headers(proposal, grant_ref))

    assert status == 200
    analysis = uploaded["report"]["scorer_unit_analysis"]
    contract = analysis["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "MATCH"
    assert contract["definition_score_coverage"]["status"] == "UNVERIFIABLE"
    assert contract["source_item_mapping"][0]["mapped_definitions"]["refs"][0]["source"]["source_value"] == (
        "def test_one():\n    assert True")
    eid = uploaded["stored"]["eid"]
    status, detail = gateway.get_json(f"/api/import/inspect/{eid}")
    assert status == 200
    assert detail == uploaded


def test_sidecar_upload_rejects_missing_wrong_bearer_bad_host_and_bad_media(gateway):
    body, proposal, grant_ref = _unit_contract_upload(gateway)
    headers = _sidecar_headers(proposal, grant_ref)

    cases = [
        ({}, False),
        ({"Authorization": "Bearer wrong"}, False),
        ({"Host": "attacker.example"}, True),
        ({"Content-Type": "text/plain"}, True),
        ({"Content-Type": "application/x-www-form-urlencoded"}, True),
        ({"Content-Type": "multipart/form-data"}, True),
        ({"Content-Type": "application/vnd.flywheel.unknown+json"}, True),
    ]
    for extra, bearer in cases:
        attempt = {**headers, **extra}
        status, response = gateway.request(
            "POST", "/api/import/inspect", body, attempt, bearer=bearer)
        assert status == 401, extra
        assert response["error"]["code"] == "AUTH_REQUIRED"
    assert not gateway.inspect_store().exists()


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
