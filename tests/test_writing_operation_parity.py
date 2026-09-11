import json

from harness import discovery_route, writing_mcp
from harness.writing_operations import SCHEMA, operation_for_http, operation_for_mcp
from harness.writing_route import writing_post
from harness.writing_types import sha256_bytes


NOW = "2026-09-08T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _post(root, path, body):
    return writing_post(path, json.dumps(body).encode("utf-8"),
        owner_ref=OWNER, state_root=root / "state", clock=lambda: NOW)


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


def _section_and_revision(root, ack):
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    section = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_recommendation", "heading": "Recommendation",
        "purpose": "state the release decision",
        "reader_entry_state": "needs a decision",
        "promises": ["states the decision"], "order_index": 1}
    proposal, status = _post(root, "/api/writing/section/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "client_request_id": "section", "section": section})
    assert status == 200
    head = _commit(root, proposal)["event_head_sha256"]
    body = "Recommendation: hold.\n"
    proposal, status = _post(root, "/api/writing/revision/prepare", {
        "journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "section_ref": "sec_recommendation",
        "body": body, "client_request_id": "revision"})
    assert status == 200
    ack = _commit(root, proposal)
    return journey, ack["event_head_sha256"], proposal, body


def _review_body(journey, head):
    return {"journey_ref": journey, "expected_event_head": head,
        "project_ref": PROJECT, "client_request_id": "review"}


def _mcp_call(name, arguments):
    response = writing_mcp.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments}})
    return json.loads(response["result"]["content"][0]["text"])


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_http_review_contract_uses_descriptor_fields_and_rejects_drift(tmp_path):
    ack = _project(tmp_path)
    journey, head, _revision, _body = _section_and_revision(tmp_path, ack)
    body = _review_body(journey, head)
    op = operation_for_http("POST", "/api/writing/review/prepare")

    assert op.schema == SCHEMA
    assert set(body) == set(op.http_required_fields())
    result, status = _post(tmp_path, op.http_path, body)
    assert status == 200
    assert result["proposal_ref"].startswith("prp_")

    result, status = _post(tmp_path, op.http_path, {**body, "extra": "x"})
    assert status == 400
    assert result["error"]["code"] == "UNKNOWN_FIELD"
    result, status = _post(tmp_path, op.http_path, {
        k: v for k, v in body.items() if k != "expected_event_head"})
    assert status == 400
    assert result["error"]["code"] == "MISSING_FIELD"
    result, status = _post(tmp_path, op.http_path, {
        **body, "expected_event_head": ["not", "a", "string"]})
    assert status == 422
    assert result["error"]["code"] == "INVALID_FIELD_TYPE"


def test_mcp_schema_projection_and_runtime_validation_share_descriptor():
    tool = next(t for t in writing_mcp.TOOLS
                if t["name"] == "writing.review_prepare")
    schema = tool["inputSchema"]
    op = operation_for_mcp("writing.review_prepare")

    assert tool["x-flywheel-operation-schema"] == SCHEMA
    assert schema["x-flywheel-operation-schema"] == SCHEMA
    assert schema["additionalProperties"] is False
    assert schema["required"] == op.mcp_required_fields()
    assert schema["properties"]["expected_event_head"]["type"] == "string"
    init = writing_mcp.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]
    assert init["capabilities"]["tools"]["x-flywheel-operation-schema"] == SCHEMA

    valid = {"home": "unused", "journey_ref": "jrn_" + "a" * 32,
        "expected_event_head": "b" * 64, "project_ref": PROJECT,
        "client_request_id": "review"}
    assert _mcp_call("writing.review_prepare", {**valid, "extra": "x"})[
        "error"]["code"] == "INVALID_ARGUMENTS"
    assert _mcp_call("writing.review_prepare", {
        k: v for k, v in valid.items() if k != "project_ref"})[
        "error"]["code"] == "INVALID_ARGUMENTS"
    assert _mcp_call("writing.review_prepare", {
        **valid, "expected_event_head": ["not", "a", "string"]})[
        "error"]["code"] == "INVALID_ARGUMENTS"


def test_openapi_enriches_writing_operations_and_keeps_scope_bounded():
    doc = discovery_route.openapi_document()
    op = doc["paths"]["/api/writing/review/prepare"]["post"]
    body = op["requestBody"]["content"]["application/json"]["schema"]

    assert doc["openapi"] == "3.1.0"
    assert discovery_route.LOWER_BOUND in doc["info"]["description"]
    assert doc["x-flywheel-typed-route-scope"] == ["writing operations"]
    assert op["x-flywheel-operation-schema"] == SCHEMA
    assert op["x-flywheel-custody"] == "private"
    assert op["x-flywheel-transport-availability"]["http"]["custody"] == (
        "private-bearer")
    assert doc["paths"]["/api/writing/status"]["get"][
        "x-flywheel-transport-availability"]["http"]["payload"] == "none"
    assert doc["paths"]["/api/writing/project"]["get"][
        "x-flywheel-transport-availability"]["http"]["payload"] == "query-string"
    assert body["additionalProperties"] is False
    assert body["required"] == [
        "journey_ref", "expected_event_head", "project_ref",
        "client_request_id"]
    assert body["properties"]["expected_event_head"]["type"] == "string"
    assert op["responses"]["400"]["content"]["application/json"]["schema"][
        "properties"]["schema"]["const"] == "flywheel.evidence-transport-error/v1"


def test_mcp_approval_refuses_grant_mint_while_http_review_commit_works(tmp_path):
    ack = _project(tmp_path)
    journey, head, _revision, _body = _section_and_revision(tmp_path, ack)
    review, status = _post(tmp_path, "/api/writing/review/prepare",
        _review_body(journey, head))
    assert status == 200
    committed = _commit(tmp_path, review)
    assert committed["event_head_sha256"] != head

    refused = _mcp_call("writing.proposal_approve", {
        "home": str(tmp_path), "proposal_ref": review["proposal_ref"]})
    op = operation_for_mcp("writing.proposal_approve")
    assert op.mcp_unavailable_reason == "APPROVAL_UNAVAILABLE"
    assert refused["error"]["code"] == "APPROVAL_UNAVAILABLE"
    assert "grant_ref" not in refused


def test_operation_projections_do_not_expose_raw_credential_fields():
    forbidden = {"api_key", "access_token", "refresh_token", "password",
        "private_key"}
    doc = discovery_route.openapi_document()
    values = [doc["paths"]["/api/writing/review/prepare"]["post"],
        writing_mcp.TOOLS]
    for value in values:
        assert not (set(_keys(value)) & forbidden)
