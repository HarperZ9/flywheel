from copy import deepcopy
import json

from harness.evidence_json import canonical_bytes
from harness.grant_route import read_proposal_record
from harness.journey_route import journey_post
from harness.writing_service import WritingService
from harness.writing_types import WRITING_DOES_NOT_PROVE

NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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


def _attempt_raw_artifact(service, journey, head, request_id, kind, opaque_ref, artifact):
    try:
        proposal = service._prepare_artifact(
            journey, head, request_id, kind, opaque_ref, artifact)
    except Exception as exc:
        return {"error": {"code": getattr(exc, "code", str(exc))}}, 403
    return _raw_commit(service, proposal)


def _project(tmp_path, source_rows=None):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    brief = {"schema": "flywheel.writing-project-brief/v1", "project_ref": PROJECT,
        "mode": "nonfiction", "form": "essay", "working_title": "V2 authority",
        "audience": "operators", "reader_job": "verify authority",
        "author_intent": "keep accepted text scoped", "voice_contract": {"style_ref": "voice"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]}
    if source_rows is None:
        source_rows = [{"source_id": "src_receipt",
        "title": "Receipt", "origin": "local", "allowed_use": "cite"}]
    sources = {"schema": "flywheel.writing-source-packet/v1", "project_ref": PROJECT,
        "source_packet_ref": "packet_main", "sources": source_rows,
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


def test_raw_diagnostic_rejects_invented_checked_semantic_summary(tmp_path):
    service, journey, head = _project(tmp_path)
    head, revision = _revision(service, journey, head, "Body without markers.\n")
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="good-diag")
    diagnostic = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"], expected_kind="diagnostic")
    diagnostic["diagnostic_ref"] = "diag_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    diagnostic["reader_state_summary"].update({"entry_state": "every assertion is supported",
        "new_information": ["meaning is preserved"], "exit_state": "no contradictions",
        "measurement_status": "checked"})
    result, status = _attempt_raw_artifact(service, journey, head, "bad-semantic",
        "diagnostic", diagnostic["diagnostic_ref"], diagnostic)
    assert status == 403
    assert result["error"]["code"] in {"DIAGNOSTIC_AUTHORITY_UNSUPPORTED",
        "ARTIFACT_INVALID", "READER_STATE_SUMMARY_AUTHORITY_INVALID"}


def test_raw_diagnostic_rejects_marker_check_without_exact_marker_span(tmp_path):
    service, journey, head = _project(tmp_path)
    head, revision = _revision(service, journey, head, "Body without markers.\n")
    bad = {"schema": "flywheel.writing-reader-flow-diagnostic/v1",
        "project_ref": PROJECT, "diagnostic_ref": "diag_cccccccccccccccccccccccccccccccc",
        "revision_ref": revision["revision_ref"], "body_sha256": revision["body_sha256"],
        "reader_state_summary": {"entry_state": "", "new_information": [],
        "exit_state": "", "kind": "reader_state_summary", "basis": "deterministic",
        "measurement_status": "unmeasured", "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "span_refs": [], "source_refs": []},
        "units": [], "problems": [], "revision_cards": [],
        "source_grounding": [{"kind": "source_marker", "status": "known_source",
        "source_id": "src_receipt", "message": "forged marker check",
        "basis": "deterministic", "measurement_status": "checked",
        "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "span_refs": [],
        "source_refs": ["src_receipt"]}], "does_not_prove": [WRITING_DOES_NOT_PROVE]}
    result, status = _attempt_raw_artifact(service, journey, head, "bad-marker",
        "diagnostic", bad["diagnostic_ref"], bad)
    assert status == 403
    assert result["error"]["code"] in {"DIAGNOSTIC_AUTHORITY_UNSUPPORTED",
        "DIAGNOSTIC_BODY_MISMATCH", "SOURCE_MARKER_MISMATCH"}


def test_review_rejects_checked_results_without_supported_analyzer_or_bindings(tmp_path):
    service, journey, head = _project(tmp_path)
    head, revision = _revision(service, journey, head, "Body.\n")
    head, _diagnostic = _diagnose(service, journey, head, revision)
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    artifact = service.artifacts.read_json(
        review["artifact_ref"], review["artifact_sha256"], expected_kind="review")
    artifact["review_ref"] = "wrev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    artifact["style_lint"] = {"status": "passed", "basis": "deterministic",
        "measurement_status": "checked", "source_refs": ["src_fictional"]}
    result, status = _attempt_raw_artifact(service, journey, head, "bad-review-style",
        "review", artifact["review_ref"], artifact)
    assert status == 403
    assert result["error"]["code"] in {"REVIEW_RESULT_UNSUPPORTED", "SOURCE_REF_INVALID"}
    artifact["review_ref"] = "wrev_cccccccccccccccccccccccccccccccc"
    artifact["style_lint"] = {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_refs": []}
    artifact["quality_measurement"] = {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "checked", "source_refs": []}
    result, status = _attempt_raw_artifact(service, journey, head, "bad-review-quality",
        "review", artifact["review_ref"], artifact)
    assert status == 403
    assert result["error"]["code"] in {"REVIEW_RESULT_UNSUPPORTED",
        "ARTIFACT_INVALID", "QUALITY_MEASUREMENT_INVALID"}


def test_review_unmeasured_flow_still_binds_empty_references(tmp_path):
    service, journey, head = _project(tmp_path)
    head, _ = _revision(service, journey, head, "Body without diagnostic.\n")
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    artifact = service.artifacts.read_json(
        review["artifact_ref"], review["artifact_sha256"], expected_kind="review")
    artifact["review_ref"] = "wrev_dddddddddddddddddddddddddddddddd"
    artifact["source_coverage"] = {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_packet_ref": "packet_fictional",
        "diagnostic_ref": "diag_unmeasured", "source_refs": ["src_fictional"]}
    result, status = _attempt_raw_artifact(service, journey, head, "bad-review-unmeasured",
        "review", artifact["review_ref"], artifact)
    assert status == 403
    assert result["error"]["code"] in {"REVIEW_SOURCE_MISMATCH", "SOURCE_REF_INVALID"}


def test_raw_diagnostic_requires_exact_unknown_marker_citation_gaps(tmp_path):
    service, journey, head = _project(tmp_path)
    body = "Known [src_receipt]. Missing [src_missing] and [src_other].\n"
    head, revision = _revision(service, journey, head, body)
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag-markers")
    diagnostic = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"],
        expected_kind="diagnostic")
    unknown = [item for item in diagnostic["source_grounding"]
        if item["status"] == "unknown_source"]
    assert [item["source_id"] for item in unknown] == ["src_missing", "src_other"]

    cases = []
    omitted = deepcopy(diagnostic); omitted["problems"] = []
    cases.append(("omit-gap", omitted))
    duplicated = deepcopy(diagnostic)
    duplicated["problems"].append(deepcopy(duplicated["problems"][0]))
    cases.append(("duplicate-gap", duplicated))
    duplicate_grounding = deepcopy(diagnostic)
    duplicate_grounding["source_grounding"].append(
        deepcopy(duplicate_grounding["source_grounding"][1]))
    cases.append(("duplicate-grounding", duplicate_grounding))
    crossed = deepcopy(diagnostic)
    crossed["problems"][0]["span_refs"] = deepcopy(
        diagnostic["source_grounding"][2]["span_refs"])
    cases.append(("crossed-gap", crossed))

    for index, (name, mutated) in enumerate(cases, 1):
        mutated["diagnostic_ref"] = f"diag_{index:032d}"
        result, status = _attempt_raw_artifact(service, journey, head,
            f"bad-{name}", "diagnostic", mutated["diagnostic_ref"], mutated)
        assert status == 403, name
        assert result["error"]["code"] in {"CITATION_GAP_MISMATCH",
            "SOURCE_MARKER_MISMATCH", "DIAGNOSTIC_AUTHORITY_UNSUPPORTED"}


def test_raw_review_requires_exact_unique_diagnostic_source_coverage(tmp_path):
    source_rows = [{"source_id": "src_receipt", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"},
        {"source_id": "src_unused", "title": "Unused", "origin": "local",
        "allowed_use": "cite"}]
    service, journey, head = _project(tmp_path, source_rows)
    head, revision = _revision(service, journey, head,
        "Only one packet source is cited. [src_receipt]\n")
    head, _diagnostic = _diagnose(service, journey, head, revision)
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    artifact = service.artifacts.read_json(
        review["artifact_ref"], review["artifact_sha256"], expected_kind="review")
    assert artifact["source_coverage"]["source_refs"] == ["src_receipt"]

    cases = [("empty", []), ("duplicate", ["src_receipt", "src_receipt"]),
        ("unused-packet-source", ["src_receipt", "src_unused"])]
    for index, (name, refs) in enumerate(cases, 1):
        mutated = deepcopy(artifact)
        mutated["review_ref"] = f"wrev_{index:032d}"
        mutated["source_coverage"]["source_refs"] = refs
        result, status = _attempt_raw_artifact(service, journey, head,
            f"bad-review-{name}", "review", mutated["review_ref"], mutated)
        assert status == 403, name
        assert result["error"]["code"] in {"REVIEW_SOURCE_MISMATCH",
            "REVIEW_SOURCE_COVERAGE_MISMATCH"}
