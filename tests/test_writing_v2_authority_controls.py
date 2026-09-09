import json

from harness.evidence_json import canonical_bytes
from harness.grant_route import read_proposal_record
from harness.journey_route import journey_post
from harness.writing_service import WritingService
from harness.writing_types import WRITING_DOES_NOT_PROVE, sha256_bytes

NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD = "card_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD2 = "card_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _flow(service, proposal):
    grant = service.approve_proposal(proposal["proposal_ref"])
    return service.commit_proposal(proposal["proposal_ref"], grant["grant_ref"])


def _raw_commit(service, proposal):
    grant = service.approve_proposal(proposal["proposal_ref"])
    record = read_proposal_record(
        proposal["proposal_ref"], owner_ref=service.owner_ref,
        state_root=service.state_root)
    return journey_post("/api/journeys/append",
        canonical_bytes({**record["request"], "grant_ref": grant["grant_ref"]}),
        owner_ref=service.owner_ref, state_root=service.state_root,
        evidence_root=service.artifacts.root, clock=service.clock)


def _project(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    brief = {"schema": "flywheel.writing-project-brief/v1", "project_ref": PROJECT,
        "mode": "nonfiction", "form": "essay", "working_title": "V2 authority",
        "audience": "operators", "reader_job": "verify authority",
        "author_intent": "keep accepted text scoped", "voice_contract": {"style_ref": "voice"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]}
    sources = {"schema": "flywheel.writing-source-packet/v1", "project_ref": PROJECT,
        "source_packet_ref": "packet_main", "sources": [{"source_id": "src_receipt",
        "title": "Receipt", "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"]}
    init = service.prepare_init(_json(tmp_path / "brief.json", brief),
        _json(tmp_path / "sources.json", sources), client_request_id="init")
    ack = _flow(service, init)
    section = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_one", "heading": "One", "purpose": "draft section",
        "reader_entry_state": "unknown", "promises": ["draft"], "order_index": 1}
    head = _flow(service, service.prepare_section(ack["journey_ref"],
        ack["event_head_sha256"], section, client_request_id="section"))["event_head_sha256"]
    return service, ack["journey_ref"], head


def _revision(service, journey, head, body, request="revision"):
    proposal = service.prepare_revision(journey, head, PROJECT, "sec_one", body,
        client_request_id=request)
    head = _flow(service, proposal)["event_head_sha256"]
    return head, proposal


def _diagnose(service, journey, head, revision):
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag-" + revision["revision_ref"][-6:])
    artifact = service.artifacts.read_json(proposal["artifact_ref"],
        proposal["artifact_sha256"], expected_kind="diagnostic")
    head = _flow(service, proposal)["event_head_sha256"]
    return head, artifact


def _target(revision, body):
    return {"section_ref": "sec_one", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 5, "end": 11,
        "selected_span_sha256": sha256_bytes(body[5:11].encode("utf-8"))}


def _card(service, journey, head, revision, diagnostic, body, card_ref=CARD):
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": card_ref, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "target": _target(revision, body), "problem": "change middle only",
        "goal": "replace selected text", "must_preserve": ["KEEP lines"],
        "allowed_operations": ["replace"], "forbidden_operations": ["change context"],
        "source_refs": ["src_receipt"], "voice_constraints": "direct",
        "does_not_prove": ["quality"]}
    proposal = service.prepare_card(journey, head, card, client_request_id=card_ref)
    head = _flow(service, proposal)["event_head_sha256"]
    return head, card


def test_supersede_scope_hold_keeps_current_and_export_bytes(tmp_path):
    service, journey, head = _project(tmp_path)
    base = "KEEP\nCHANGE\nKEEP\n"
    head, revision = _revision(service, journey, head, base)
    head, diagnostic = _diagnose(service, journey, head, revision)
    head, _ = _card(service, journey, head, revision, diagnostic, base)
    candidate = service.prepare_candidate(journey, head, PROJECT, CARD,
        "OUTSIDE SCOPE\n", client_request_id="candidate")
    assert candidate["scope_verdict"] == "HOLD"
    head = _flow(service, candidate)["event_head_sha256"]
    supersede = service.prepare_decision(journey, head, PROJECT, decision="supersede",
        candidate_ref=candidate["candidate_ref"], client_request_id="supersede")
    head = _flow(service, supersede)["event_head_sha256"]
    state = service.project_state(journey)
    assert state["sections"]["sec_one"]["current_body"] == base
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    head = _flow(service, review)["event_head_sha256"]
    export = service.prepare_export(journey, head, PROJECT,
        out_ref="article", client_request_id="export")
    _flow(service, export)
    manifest = service.artifacts.read_json(export["artifact_ref"],
        export["artifact_sha256"], expected_kind="export")
    assert service.read_text(manifest["manuscript_ref"],
        manifest["manuscript_sha256"]) == base


def test_raw_diagnostic_inner_body_and_source_claims_are_revalidated(tmp_path):
    service, journey, head = _project(tmp_path)
    body = "Body with [src_receipt].\n"
    head, revision = _revision(service, journey, head, body)
    bad = {"schema": "flywheel.writing-reader-flow-diagnostic/v1", "project_ref": PROJECT,
        "diagnostic_ref": "diag_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "revision_ref": revision["revision_ref"], "body_sha256": revision["body_sha256"],
        "reader_state_summary": {"entry_state": "", "new_information": [],
        "exit_state": "", "kind": "reader_state", "basis": "author_annotation",
        "measurement_status": "reported", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "span_refs": [], "source_refs": []},
        "units": [{"unit_ref": "unit_bad", "kind": "paragraph", "start": 900,
        "end": 950, "excerpt": "TEXT THAT DOES NOT EXIST", "topic_anchor": "reported",
        "comment": "reported", "handoff_to_next": "reported", "pattern": "anchored",
        "heuristic_strength": "author_annotation", "basis": "author_annotation",
        "measurement_status": "reported", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "span_refs": [],
        "source_refs": ["src_missing"]}], "problems": [], "revision_cards": [],
        "source_grounding": [{"kind": "none", "status": "known_source",
        "source_id": "src_missing", "message": "forged", "basis": "deterministic",
        "measurement_status": "checked", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "span_refs": [],
        "source_refs": ["src_missing"]}], "does_not_prove": [WRITING_DOES_NOT_PROVE]}
    proposal = service._prepare_artifact(journey, head, "bad-diag", "diagnostic",
        bad["diagnostic_ref"], bad)
    result, status = _raw_commit(service, proposal)
    assert status == 403
    assert result["error"]["code"] in {"DIAGNOSTIC_BODY_MISMATCH", "SOURCE_REF_INVALID"}


def test_card_requires_known_diagnostic_and_packet_source(tmp_path):
    service, journey, head = _project(tmp_path)
    body = "KEEP\nCHANGE\nKEEP\n"
    head, revision = _revision(service, journey, head, body)
    bad_card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD, "diagnostic_ref": "diag_ffffffffffffffffffffffffffffffff",
        "target": _target(revision, body), "problem": "change middle only",
        "goal": "replace selected text", "must_preserve": ["KEEP lines"],
        "allowed_operations": ["replace"], "forbidden_operations": ["change context"],
        "source_refs": ["src_missing"], "voice_constraints": "direct",
        "does_not_prove": ["quality"]}
    proposal = service._prepare_artifact(journey, head, "bad-card", "card",
        bad_card["card_ref"], bad_card)
    result, status = _raw_commit(service, proposal)
    assert status == 403
    assert result["error"]["code"] in {"DIAGNOSTIC_REF_INVALID", "SOURCE_REF_INVALID"}


def test_review_requires_diagnostic_for_current_revision(tmp_path):
    service, journey, head = _project(tmp_path)
    head, first = _revision(service, journey, head, "first\n", "first")
    head, diagnostic = _diagnose(service, journey, head, first)
    head, second = _revision(service, journey, head, "second\n", "second")
    review = {"schema": "flywheel.writing-review/v1", "project_ref": PROJECT,
        "review_ref": "wrev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "revision_refs": [second["revision_ref"]],
        "reader_flow_ref": diagnostic["diagnostic_ref"],
        "source_coverage": {"status": "checked", "basis": "deterministic",
        "measurement_status": "checked", "source_packet_ref": "packet_main",
        "diagnostic_ref": diagnostic["diagnostic_ref"], "source_refs": ["src_receipt"]},
        "style_lint": {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_refs": []},
        "scope_preservation": {"status": "checked", "basis": "deterministic",
        "measurement_status": "checked", "decision_refs": []},
        "quality_measurement": {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_refs": []},
        "blocking_items": [], "does_not_prove": [WRITING_DOES_NOT_PROVE]}
    proposal = service._prepare_artifact(journey, head, "bad-review", "review",
        review["review_ref"], review)
    result, status = _raw_commit(service, proposal)
    assert status == 403
    assert result["error"]["code"] == "REVIEW_READER_FLOW_MISMATCH"


def test_same_text_new_revision_gets_distinct_diagnostic_identity(tmp_path):
    service, journey, head = _project(tmp_path)
    head, first = _revision(service, journey, head, "same\n", "first")
    head, diag1 = _diagnose(service, journey, head, first)
    head, second = _revision(service, journey, head, "same\n", "second")
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        second["revision_ref"], client_request_id="diag-second")
    diag2 = service.artifacts.read_json(proposal["artifact_ref"],
        proposal["artifact_sha256"], expected_kind="diagnostic")
    assert diag2["diagnostic_ref"] != diag1["diagnostic_ref"]
    _flow(service, proposal)


def test_export_allows_one_megabyte_manuscript_contract(tmp_path):
    service, journey, head = _project(tmp_path)
    body = "a" * 140_000
    head, _ = _revision(service, journey, head, body, "large-one")
    second = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_two", "heading": "Two", "purpose": "draft section",
        "reader_entry_state": "unknown", "promises": ["draft"], "order_index": 2}
    head = _flow(service, service.prepare_section(journey, head, second,
        client_request_id="section-two"))["event_head_sha256"]
    proposal = service.prepare_revision(journey, head, PROJECT, "sec_two",
        body + "b", client_request_id="large-two")
    head = _flow(service, proposal)["event_head_sha256"]
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    head = _flow(service, review)["event_head_sha256"]
    export = service.prepare_export(journey, head, PROJECT,
        out_ref="large", client_request_id="export")
    _flow(service, export)
    manifest = service.artifacts.read_json(export["artifact_ref"],
        export["artifact_sha256"], expected_kind="export")
    assert manifest["manuscript_sha256"] == sha256_bytes((body + "\n" + body + "b").encode())
