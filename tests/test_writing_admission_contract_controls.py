import json

import pytest

from harness.writing_service import WritingService
from harness.writing_types import WritingTypeError, sha256_bytes, validate_artifact

NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _flow(service, proposal):
    grant = service.approve_proposal(proposal["proposal_ref"])
    return service.commit_proposal(proposal["proposal_ref"], grant["grant_ref"])


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _brief():
    return {"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Release evidence", "audience": "operators",
        "reader_job": "decide whether the release is safe",
        "author_intent": "bind claims to receipts",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]}


def _source_packet():
    return {"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["source truth"]}


def _section():
    return {"schema": "flywheel.writing-section/v1",
        "project_ref": PROJECT, "section_ref": "sec_recommendation",
        "heading": "Recommendation", "purpose": "name the release decision",
        "reader_entry_state": "needs the conclusion",
        "promises": ["states the decision"], "order_index": 0}


def test_v2_authority_vocabulary_and_analyzer_provenance():
    rev_a = "rev_" + "a" * 32
    base = {"kind": "source_marker", "basis": "none",
        "measurement_status": "unsupported", "base_revision_ref": rev_a,
        "base_body_sha256": "a" * 64, "span_refs": [], "source_refs": []}
    diagnostic = {"schema": "flywheel.writing-reader-flow-diagnostic/v1",
        "project_ref": PROJECT, "diagnostic_ref": "diag_" + "a" * 32,
        "revision_ref": rev_a, "body_sha256": "a" * 64,
        "reader_state_summary": {"kind": "reader_state_summary",
        "basis": "none", "measurement_status": "unmeasured",
        "base_revision_ref": rev_a, "base_body_sha256": "a" * 64,
        "span_refs": [], "source_refs": [], "entry_state": "",
        "new_information": [], "exit_state": ""},
        "units": [], "problems": [], "revision_cards": [],
        "source_grounding": [{**base, "status": "no_source_markers",
        "message": "no bracketed source markers were present"}],
        "does_not_prove": ["quality"]}
    assert validate_artifact(diagnostic, "diagnostic")["source_grounding"][0][
        "measurement_status"] == "unsupported"
    model_summary = {**diagnostic["reader_state_summary"],
        "basis": "model_annotation", "measurement_status": "reported",
        "entry_state": "annotated"}
    with pytest.raises(WritingTypeError, match="ANALYZER_PROVENANCE_INVALID"):
        validate_artifact({**diagnostic, "reader_state_summary": model_summary},
            "diagnostic")
    model_summary = {**model_summary, "analyzer_ref": "reader-flow-analyzer",
        "analyzer_sha256": "b" * 64}
    assert validate_artifact({**diagnostic, "reader_state_summary": model_summary},
        "diagnostic")["reader_state_summary"]["analyzer_ref"] == "reader-flow-analyzer"


def test_revision_admission_reports_crlf_conversion_and_coordinate_basis(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    init = service.prepare_init(_write(tmp_path / "brief.json", _brief()),
        _write(tmp_path / "sources.json", _source_packet()), client_request_id="init")
    ack = _flow(service, init)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    head = _flow(service, service.prepare_section(
        journey, head, _section(), client_request_id="section"))["event_head_sha256"]
    raw = b"Alpha\r\nBeta\rGamma\n"
    proposal = service.prepare_revision(journey, head, PROJECT,
        "sec_recommendation", raw, client_request_id="crlf")
    artifact = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"], expected_kind="revision")
    receipt = artifact["text_admission"]
    assert receipt["coordinate_type"] == "unicode_codepoint"
    assert receipt["coordinate_basis"] == "admitted_lf_text"
    assert receipt["converted_crlf"] is True
    assert receipt["converted_cr"] is True
    assert receipt["input_sha256"] == sha256_bytes(raw)
    assert receipt["admitted_sha256"] == artifact["body_sha256"]
    preview = service.proposal_get(proposal["proposal_ref"])
    assert preview["approval_preview"]["text_admission"] == receipt
    assert service.read_text(artifact["body_ref"], artifact["body_sha256"]) == "Alpha\nBeta\nGamma\n"
