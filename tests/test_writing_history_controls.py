import json

from harness.writing_service import WritingService
from harness.writing_types import sha256_bytes


NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD = "card_" + "2" * 32


def _json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _flow(service, proposal):
    grant = service.approve_proposal(proposal["proposal_ref"])
    return service.commit_proposal(proposal["proposal_ref"], grant["grant_ref"])


def _project(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    brief = _json(tmp_path / "brief.json", {"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Ordered changes", "audience": "operators",
        "reader_job": "verify revision order", "author_intent": "record ordered changes",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]})
    sources = _json(tmp_path / "sources.json", {"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_one", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"]})
    ack = _flow(service, service.prepare_init(brief, sources, client_request_id="init"))
    section = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_one", "heading": "One", "purpose": "record the draft",
        "reader_entry_state": "unknown", "promises": ["private draft"],
        "order_index": 1}
    head = _flow(service, service.prepare_section(
        ack["journey_ref"], ack["event_head_sha256"], section,
        client_request_id="section"))["event_head_sha256"]
    return service, ack["journey_ref"], head


def _revision(service, journey, head, body, request_id):
    proposal = service.prepare_revision(
        journey, head, PROJECT, "sec_one", body, client_request_id=request_id)
    head = _flow(service, proposal)["event_head_sha256"]
    return head, proposal


def _diagnose(service, journey, head, revision):
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag-" + revision["revision_ref"][-6:])
    artifact = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"], expected_kind="diagnostic")
    return _flow(service, proposal)["event_head_sha256"], artifact


def test_repeated_manual_revisions_update_current_after_restart(tmp_path):
    service, journey, head = _project(tmp_path)
    head, first = _revision(service, journey, head, "first\n", "rev-one")
    head, second = _revision(service, journey, head, "second\n", "rev-two")

    state = WritingService(tmp_path / "home", clock=lambda: NOW).project_state(journey)

    assert first["revision_ref"] in state["accepted_revision_refs_by_section"]["sec_one"]
    assert second["revision_ref"] in state["accepted_revision_refs_by_section"]["sec_one"]
    assert state["sections"]["sec_one"]["current_revision_ref"] == second["revision_ref"]
    assert state["sections"]["sec_one"]["current_body"] == "second\n"


def test_ai_accept_then_manual_save_can_rollback_to_candidate_after_restart(tmp_path):
    service, journey, head = _project(tmp_path)
    head, original = _revision(service, journey, head, "original\n", "rev-original")
    head, diagnostic = _diagnose(service, journey, head, original)
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Replace section.", "goal": "replace selected text",
        "must_preserve": ["outside selected span"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_one"],
        "voice_constraints": "direct", "target": {"section_ref": "sec_one",
        "base_revision_ref": original["revision_ref"], "base_body_sha256": original["body_sha256"],
        "coordinate_type": "unicode_codepoint",
        "start": 0, "end": len("original\n"), "selected_span_sha256": sha256_bytes(b"original\n")},
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(
        journey, head, PROJECT, CARD, "accepted\n",
        client_request_id="candidate")
    head = _flow(service, candidate)["event_head_sha256"]
    head = _flow(service, service.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"],
        client_request_id="accept"))["event_head_sha256"]
    restarted = WritingService(tmp_path / "home", clock=lambda: NOW)
    accepted = restarted.project_state(journey)
    candidate_revision = accepted["sections"]["sec_one"]["current_revision_ref"]
    assert candidate_revision in accepted["revisions"]
    assert accepted["revisions"][candidate_revision]["accepted_candidate_ref"] == candidate["candidate_ref"]
    head, manual = _revision(restarted, journey, head, "manual\n", "rev-manual")
    state = restarted.project_state(journey)
    assert state["revisions"][manual["revision_ref"]]["base_revision_ref"] == candidate_revision
    rollback = restarted.prepare_decision(
        journey, head, PROJECT, decision="rollback", section_ref="sec_one",
        to_revision_ref=candidate_revision, client_request_id="rollback")
    _flow(restarted, rollback)
    after = WritingService(tmp_path / "home", clock=lambda: NOW).project_state(journey)
    assert after["sections"]["sec_one"]["current_body"] == "accepted\n"


def test_export_uses_saved_heads_not_unaccepted_candidates(tmp_path):
    service, journey, head = _project(tmp_path)
    head, original = _revision(service, journey, head, "original\n", "rev-original")
    head, diagnostic = _diagnose(service, journey, head, original)
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Replace section.", "goal": "replace selected text",
        "must_preserve": ["outside selected span"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_one"],
        "voice_constraints": "direct", "target": {"section_ref": "sec_one",
        "base_revision_ref": original["revision_ref"], "base_body_sha256": original["body_sha256"],
        "coordinate_type": "unicode_codepoint",
        "start": 0, "end": len("original\n"), "selected_span_sha256": sha256_bytes(b"original\n")},
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(
        journey, head, PROJECT, CARD, "unaccepted\n",
        client_request_id="candidate")
    head = _flow(service, candidate)["event_head_sha256"]
    export = service.prepare_export(
        journey, head, PROJECT, out_ref="article", client_request_id="export")
    _flow(service, export)
    state = WritingService(tmp_path / "home", clock=lambda: NOW).project_state(journey)
    assert service.read_text(state["exports"][-1]["manuscript_ref"]) == "original\n"
