import json

from harness.gateway_custody import is_private
from harness.writing_route import writing_get, writing_post
from harness.writing_types import sha256_bytes

NOW = "2026-09-08T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _post(root, path, body):
    return writing_post(path, json.dumps(body).encode("utf-8"),
        owner_ref=OWNER, state_root=root / "state", clock=lambda: NOW)


def _get(root, path):
    return writing_get(path, owner_ref=OWNER,
        state_root=root / "state", clock=lambda: NOW)


def _commit(root, proposal):
    grant, status = _post(root, "/api/writing/proposal/approve", {
        "proposal_ref": proposal["proposal_ref"]})
    assert status == 200
    ack, status = _post(root, "/api/writing/proposal/commit", {
        "proposal_ref": proposal["proposal_ref"],
        "grant_ref": grant["grant_ref"]})
    assert status == 200
    return ack


def _project(root):
    brief = {"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Release evidence", "audience": "operators",
        "reader_job": "decide whether evidence is sufficient",
        "author_intent": "make a bounded release recommendation",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]}
    packet = {"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["source interpretation"]}
    proposal, status = _post(root, "/api/writing/init/prepare", {
        "brief": brief, "source_packet": packet, "client_request_id": "init"})
    assert status == 200
    return _commit(root, proposal)


def _section(root, journey, head):
    proposal, status = _post(root, "/api/writing/section/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "client_request_id": "section", "section": {
        "schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_recommendation", "heading": "Recommendation",
        "purpose": "state the release decision",
        "reader_entry_state": "needs a decision",
        "promises": ["states the decision"], "order_index": 1}})
    assert status == 200
    return _commit(root, proposal)["event_head_sha256"]


def _revision(root, journey, head, body, request_id):
    proposal, status = _post(root, "/api/writing/revision/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "section_ref": "sec_recommendation",
        "body": body, "client_request_id": request_id})
    assert status == 200
    ack = _commit(root, proposal)
    return ack["event_head_sha256"], proposal


def test_writing_routes_are_private_and_project_json_inputs_are_bounded(tmp_path):
    assert is_private("/api/writing/status")
    ack = _project(tmp_path)
    body, status = _get(tmp_path,
        f"/api/writing/project?journey_ref={ack['journey_ref']}")
    assert status == 200
    assert body["source_packet"]["sources"][0]["source_id"] == "src_receipt"
    assert body["sections"] == []
    assert "owner_" not in json.dumps(body)


def test_writing_route_flow_previews_exact_diff_and_exports_saved_state(tmp_path):
    ack = _project(tmp_path)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    head = _section(tmp_path, journey, head)
    head, revision = _revision(tmp_path, journey, head,
        "Recommendation: hold.\n", "revision")
    diag, status = _post(tmp_path, "/api/writing/diagnose/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "revision_ref": revision["revision_ref"],
        "client_request_id": "diagnose"})
    assert status == 200
    head = _commit(tmp_path, diag)["event_head_sha256"]
    target = {"section_ref": "sec_recommendation",
        "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"],
        "coordinate_type": "unicode_codepoint", "start": 0,
        "end": len("Recommendation: hold.\n"),
        "selected_span_sha256": sha256_bytes(b"Recommendation: hold.\n")}
    card, status = _post(tmp_path, "/api/writing/card/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "client_request_id": "card", "card": {
        "schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT, "card_ref": "card_" + "a" * 32,
        "diagnostic_ref": diag["artifact_id"], "target": target,
        "problem": "Decision is outdated.",
        "goal": "replace only the recommendation sentence",
        "must_preserve": ["source packet"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change sources"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct", "does_not_prove": ["quality"]}})
    assert status == 200
    head = _commit(tmp_path, card)["event_head_sha256"]
    candidate, status = _post(tmp_path, "/api/writing/candidate/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "card_ref": "card_" + "a" * 32,
        "body": "Recommendation: release.\n",
        "client_request_id": "candidate"})
    assert status == 200
    preview, status = _post(tmp_path, "/api/writing/proposal/get", {
        "proposal_ref": candidate["proposal_ref"]})
    assert status == 200
    diff = preview["approval_preview"]["exact_diff"]
    assert diff["before"] == "Recommendation: hold.\n"
    assert diff["after"] == "Recommendation: release.\n"
    assert preview["approval_preview"]["stored_scope_receipt_matches"] is True
    head = _commit(tmp_path, candidate)["event_head_sha256"]
    decision, status = _post(tmp_path, "/api/writing/decision/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "decision": "accept",
        "candidate_ref": candidate["candidate_ref"],
        "client_request_id": "accept"})
    assert status == 200
    head = _commit(tmp_path, decision)["event_head_sha256"]
    export, status = _post(tmp_path, "/api/writing/export/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "out_ref": "article-final",
        "client_request_id": "export"})
    assert status == 200
    export_bound_head = head
    head = _commit(tmp_path, export)["event_head_sha256"]
    project, status = _get(tmp_path,
        f"/api/writing/project?journey_ref={journey}")
    assert status == 200
    assert project["sections"][0]["current_body"] == "Recommendation: release.\n"
    assert project["exports"][-1]["event_head_sha256"] == export_bound_head
    assert project["event_head_sha256"] == head


def test_writing_route_returns_typed_errors_without_tracebacks(tmp_path):
    body, status = writing_post("/api/writing/init/prepare", b"{",
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    assert status == 400
    assert body["error"]["code"] == "INVALID_JSON"
    assert "Traceback" not in json.dumps(body)
    ack = _project(tmp_path)
    result, status = _post(tmp_path, "/api/writing/export/prepare", {
        "journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "project_ref": PROJECT, "out_ref": "../escape",
        "client_request_id": "bad-export"})
    assert status in {400, 422}
    assert result["error"]["code"] != "STORE_COMMIT_FAILED"
