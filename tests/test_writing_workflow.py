import json
import pytest
from harness.writing_service import WritingError, WritingService
from harness.writing_types import sha256_bytes
from harness.evidence_json import canonical_bytes
from harness.grant_route import read_proposal_record
from harness.journey_route import journey_post
NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD_A = "card_" + "a" * 32
CARD_B = "card_" + "b" * 32
CARD_C = "card_" + "c" * 32
def _json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path
def _flow(service, proposal):
    approved = service.approve_proposal(proposal["proposal_ref"])
    return service.commit_proposal(proposal["proposal_ref"], approved["grant_ref"])
def _project(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    brief = _json(tmp_path / "brief.json", {
        "schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT,
        "mode": "nonfiction",
        "form": "essay",
        "working_title": "Release evidence",
        "audience": "operators",
        "reader_job": "decide whether release evidence is sufficient",
        "author_intent": "decide whether release evidence is sufficient",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main",
        "writing_profile": "nonfiction",
        "does_not_prove": ["source packet truth"],
    })
    source = _json(tmp_path / "sources.json", {
        "schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT,
        "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_receipt", "title": "Receipt",
                     "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["source interpretation"],
    })
    ack = _flow(service, service.prepare_init(
        brief, source, client_request_id="init-1"))
    return service, ack["journey_ref"], ack["event_head_sha256"]
def _section(service, journey, head, section_ref, position):
    proposal = service.prepare_section(journey, head, {
        "schema": "flywheel.writing-section/v1",
        "project_ref": PROJECT,
        "section_ref": section_ref,
        "heading": section_ref.removeprefix("sec_").replace("_", " ").title(),
        "purpose": "record the section draft",
        "reader_entry_state": "reader needs this section",
        "promises": ["section draft remains author controlled"],
        "order_index": position,
    }, client_request_id=f"section-{position}")
    ack = _flow(service, proposal)
    return ack["event_head_sha256"]
def _revision(service, journey, head, section_ref, body, request_id):
    proposal = service.prepare_revision(
        journey, head, PROJECT, section_ref, body, client_request_id=request_id)
    ack = _flow(service, proposal)
    return ack["event_head_sha256"], proposal
def _diagnose(service, journey, head, revision):
    proposal = service.prepare_diagnose(
        journey, head, PROJECT, revision["revision_ref"],
        client_request_id="diag-" + revision["revision_ref"][-6:])
    artifact = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"], expected_kind="diagnostic")
    return _flow(service, proposal)["event_head_sha256"], artifact
def test_author_workflow_preserves_scoped_evidence_and_survives_restart(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_evidence", 1)
    head = _section(service, journey, head, "sec_recommendation", 2)
    evidence = "Receipt A passed download-back.\nReceipt B passed CI.\n"
    head, evidence_rev = _revision(
        service, journey, head, "sec_evidence", evidence, "rev-evidence")
    original = "Recommendation: hold until release assets match.\n"
    head, original_rev = _revision(
        service, journey, head, "sec_recommendation", original, "rev-original")
    head, diagnostic = _diagnose(service, journey, head, original_rev)
    restarted = WritingService(tmp_path / "home", clock=lambda: NOW)
    state = restarted.project_state(journey)
    assert state["sections"]["sec_evidence"]["current_body"] == evidence
    assert state["sections"]["sec_recommendation"]["current_body"] == original
    selected = original.strip()
    card = {
        "schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT,
        "card_ref": CARD_A,
        "diagnostic_ref": diagnostic["diagnostic_ref"],
        "target": {
            "section_ref": "sec_recommendation",
            "base_revision_ref": original_rev["revision_ref"],
            "base_body_sha256": original_rev["body_sha256"],
            "coordinate_type": "unicode_codepoint",
            "start": original.index(selected),
            "end": original.index(selected) + len(selected),
            "selected_span_sha256": sha256_bytes(selected.encode()),
        },
        "problem": "Recommendation should reflect completed download-back.",
        "goal": "update only the recommendation sentence",
        "must_preserve": ["evidence section", "outside selected span"],
        "allowed_operations": ["replace"],
        "forbidden_operations": ["change evidence"],
        "source_refs": ["src_receipt"],
        "voice_constraints": "direct",
        "does_not_prove": ["the card is semantically correct"],
    }
    head = _flow(restarted, restarted.prepare_card(
        journey, head, card, client_request_id="card-1"))["event_head_sha256"]
    revised = "Recommendation: release after all public assets match.\n"
    candidate = restarted.prepare_candidate(
        journey, head, PROJECT, CARD_A, revised,
        client_request_id="candidate-good")
    assert candidate["scope_verdict"] == "PASS"
    head = _flow(restarted, candidate)["event_head_sha256"]
    accept = restarted.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept-good")
    approved = restarted.approve_proposal(accept["proposal_ref"])
    ack = restarted.commit_proposal(accept["proposal_ref"], approved["grant_ref"])
    replay = restarted.commit_proposal(accept["proposal_ref"], approved["grant_ref"])
    assert replay["event_head_sha256"] == ack["event_head_sha256"]
    head = ack["event_head_sha256"]
    assert restarted.project_state(journey)["sections"][
        "sec_recommendation"]["current_body"] == revised
    assert restarted.project_state(journey)["sections"]["sec_evidence"][
        "current_body"] == evidence
    stale = restarted.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept-stale")
    with pytest.raises(WritingError, match="HEAD_CONFLICT"):
        _flow(restarted, stale)
    rollback = restarted.prepare_decision(
        journey, head, PROJECT, decision="rollback",
        section_ref="sec_recommendation",
        to_revision_ref=original_rev["revision_ref"],
        client_request_id="rollback-1")
    head = _flow(restarted, rollback)["event_head_sha256"]
    assert restarted.project_state(journey)["sections"][
        "sec_recommendation"]["current_body"] == original
    reaccept = restarted.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept-again")
    head = _flow(restarted, reaccept)["event_head_sha256"]
    assert restarted.project_state(journey)["sections"][
        "sec_recommendation"]["current_body"] == revised
    review = restarted.prepare_review(
        journey, head, PROJECT, client_request_id="review-1")
    head = _flow(restarted, review)["event_head_sha256"]
    export = restarted.prepare_export(
        journey, head, PROJECT, out_ref="article-final",
        client_request_id="export-1")
    head = _flow(restarted, export)["event_head_sha256"]
    state = restarted.project_state(journey)
    assert restarted.read_text(state["exports"][-1]["manuscript_ref"]) == (
        evidence + "\n" + revised)
    with pytest.raises(WritingError, match="EXPORT_TARGET_EXISTS"):
        restarted.prepare_export(
            journey, head, PROJECT, out_ref="article-final",
            client_request_id="export-repeat")
def test_approved_decision_refuses_candidate_artifact_drift(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_recommendation", 1)
    original = "Recommendation: hold.\n"
    head, original_rev = _revision(
        service, journey, head, "sec_recommendation", original, "rev-original")
    head, diagnostic = _diagnose(service, journey, head, original_rev)
    card = {
        "schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT,
        "card_ref": CARD_B,
        "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Change recommendation.",
        "goal": "update only the recommendation",
        "must_preserve": ["outside selected span"],
        "allowed_operations": ["replace"],
        "forbidden_operations": ["change evidence"],
        "source_refs": ["src_receipt"],
        "voice_constraints": "direct",
        "target": {
            "section_ref": "sec_recommendation",
            "base_revision_ref": original_rev["revision_ref"],
            "base_body_sha256": original_rev["body_sha256"],
            "coordinate_type": "unicode_codepoint",
            "start": 0,
            "end": len(original),
            "selected_span_sha256": sha256_bytes(original.encode()),
        },
        "does_not_prove": ["quality"],
    }
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(
        journey, head, PROJECT, CARD_B, "Recommendation: ship.\n",
        client_request_id="candidate")
    head = _flow(service, candidate)["event_head_sha256"]
    accept = service.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept")
    approved = service.approve_proposal(accept["proposal_ref"])
    path = service.artifacts.path_for_ref(candidate["artifact_ref"])
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["scope_receipt"]["verdict"] = "PASS"
    tampered["candidate_body_sha256"] = "0" * 64
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(WritingError, match="ARTIFACT_DRIFT"):
        service.commit_proposal(accept["proposal_ref"], approved["grant_ref"])
def test_projection_rejects_valid_historical_artifact_drift(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    head, revision = _revision(service, journey, head, "sec_one", "ORIGINAL\n", "rev")
    body = service.artifacts.write_text(
        service.owner_ref, PROJECT, "body", "tampered", "REPLACEMENT\n")
    path = service.artifacts.path_for_ref(revision["artifact_ref"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["body_ref"] = body["artifact_ref"]
    payload["body_sha256"] = body["artifact_sha256"]
    path.write_bytes(canonical_bytes(payload))
    restarted = WritingService(tmp_path / "home", clock=lambda: NOW)
    with pytest.raises(WritingError, match="ARTIFACT_DRIFT"):
        restarted.project_state(journey)
    with pytest.raises(WritingError, match="ARTIFACT_DRIFT"):
        restarted.prepare_export(journey, head, PROJECT, out_ref="out",
                                 client_request_id="export")
def test_generic_journey_append_cannot_bypass_writing_decision_checks(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    base = "KEEP\nCHANGE\nKEEP\n"
    head, revision = _revision(service, journey, head, "sec_one", base, "base")
    head, diagnostic = _diagnose(service, journey, head, revision)
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD_C, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Change middle only.", "goal": "replace selected text",
        "must_preserve": ["KEEP lines"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct",
        "target": {"section_ref": "sec_one", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 5, "end": 11,
        "selected_span_sha256": sha256_bytes(b"CHANGE")},
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(
        journey, head, PROJECT, CARD_C, "OUT OF SCOPE\n",
        client_request_id="candidate")
    assert candidate["scope_verdict"] == "HOLD"
    head = _flow(service, candidate)["event_head_sha256"]
    proposal = service.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept")
    grant = service.approve_proposal(proposal["proposal_ref"])
    record = read_proposal_record(
        proposal["proposal_ref"], owner_ref=service.owner_ref,
        state_root=service.state_root)
    result, status = journey_post(
        "/api/journeys/append",
        canonical_bytes({**record["request"], "grant_ref": grant["grant_ref"]}),
        owner_ref=service.owner_ref, state_root=service.state_root,
        evidence_root=service.artifacts.root, clock=service.clock)
    assert status == 403
    assert result["error"]["code"] == "SCOPE_VIOLATION"
def test_rollback_requires_same_section_previously_accepted_revision(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    head = _section(service, journey, head, "sec_two", 2)
    head, first = _revision(service, journey, head, "sec_one", "ONE\n", "one")
    head, second = _revision(service, journey, head, "sec_two", "TWO\n", "two")
    with pytest.raises(WritingError, match="ROLLBACK_TARGET_INVALID"):
        service.prepare_decision(
            journey, head, PROJECT, decision="rollback",
            section_ref="sec_one", to_revision_ref=second["revision_ref"],
            client_request_id="cross-section")
    candidate_body = "ONE CHANGED\n"
    head, diagnostic = _diagnose(service, journey, head, first)
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD_B, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Change.", "goal": "replace section text",
        "must_preserve": ["outside selected span"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct",
        "target": {"section_ref": "sec_one", "base_revision_ref": first["revision_ref"],
        "base_body_sha256": first["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 0, "end": len("ONE\n"),
        "selected_span_sha256": first["body_sha256"]},
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(
        journey, head, PROJECT, CARD_B, candidate_body,
        client_request_id="candidate")
    head = _flow(service, candidate)["event_head_sha256"]
    head = _flow(service, service.prepare_decision(
        journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept"))["event_head_sha256"]
    rollback = service.prepare_decision(
        journey, head, PROJECT, decision="rollback",
        section_ref="sec_one", to_revision_ref=first["revision_ref"],
        client_request_id="rollback")
    assert rollback["approval_required"] is True
