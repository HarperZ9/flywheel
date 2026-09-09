import json
import os
import subprocess
import sys

import pytest

from harness.evidence_json import canonical_bytes
from harness.grant_route import read_proposal_record
from harness.journey_route import journey_post
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


def _target(revision):
    return {"section_ref": "sec_recommendation",
        "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 0,
        "end": len("Recommendation: hold.\n"),
        "selected_span_sha256": revision["body_sha256"]}


def test_v2_artifact_shapes_validate_and_reduced_shapes_fail():
    rev_a = "rev_" + "a" * 32; rev_b = "rev_" + "b" * 32
    diag_a = "diag_" + "a" * 32; card_a = "card_" + "a" * 32
    cand_a = "cand_" + "a" * 32; dec_a = "dec_" + "a" * 32
    wrev_a = "wrev_" + "a" * 32; wexp_a = "wexp_" + "a" * 32
    target = {"section_ref": "sec_recommendation",
        "base_revision_ref": rev_a,
        "base_body_sha256": "a" * 64, "coordinate_type": "unicode_codepoint", "start": 0, "end": 4,
        "selected_span_sha256": "b" * 64}
    receipt = {"verdict": "PASS", "failure_reasons": [], "target": target,
        "replacement_text": "ship", "does_not_prove": "scope is not quality"}
    admission_a = {"coordinate_type": "unicode_codepoint",
        "coordinate_basis": "admitted_lf_text", "input_newline": "lf",
        "stored_newline": "lf", "converted_crlf": False,
        "converted_cr": False, "input_sha256": "a" * 64,
        "admitted_sha256": "a" * 64}
    admission_b = {**admission_a, "input_sha256": "b" * 64,
        "admitted_sha256": "b" * 64}
    authority = {"kind": "reader_state_summary", "basis": "deterministic",
        "measurement_status": "unmeasured", "base_revision_ref": rev_a,
        "base_body_sha256": "a" * 64, "span_refs": [], "source_refs": []}
    artifacts = [
        (_section(), "section"),
        ({"schema": "flywheel.writing-revision/v1", "project_ref": PROJECT,
        "section_ref": "sec_recommendation", "revision_ref": rev_a,
        "base_revision_ref": None, "body_ref": "body_a", "body_sha256": "a" * 64,
        "word_count": 2, "author_supplied": True, "scope_refs": [],
        "text_admission": admission_a, "does_not_prove": ["quality"]}, "revision"),
        ({"schema": "flywheel.writing-reader-flow-diagnostic/v1",
        "project_ref": PROJECT, "diagnostic_ref": diag_a,
        "revision_ref": rev_a, "body_sha256": "a" * 64,
        "reader_state_summary": {**authority, "entry_state": "",
        "new_information": [], "exit_state": ""},
        "units": [],
        "problems": [], "revision_cards": [], "source_grounding": [],
        "does_not_prove": ["quality"]}, "diagnostic"),
        ({"schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT, "card_ref": card_a, "diagnostic_ref": diag_a,
        "target": target, "problem": "stale recommendation",
        "goal": "update only the recommendation",
        "must_preserve": ["outside target"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change other sections"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct", "does_not_prove": ["quality"]}, "card"),
        ({"schema": "flywheel.writing-revision-candidate/v1",
        "project_ref": PROJECT, "candidate_ref": cand_a, "card_ref": card_a,
        "base_revision_ref": rev_a, "candidate_revision_ref": rev_b,
        "candidate_body_ref": "body_b", "candidate_body_sha256": "b" * 64,
        "diff_summary": "updates recommendation", "out_of_scope_changes": [],
        "created_by": "fixture", "scope_receipt": receipt, "text_admission": admission_b,
        "does_not_prove": ["quality"]}, "candidate"),
        ({"schema": "flywheel.writing-decision/v1", "project_ref": PROJECT,
        "decision_ref": dec_a, "decision": "accept",
        "section_ref": "sec_recommendation", "candidate_ref": cand_a,
        "candidate_artifact_ref": "candidate_a", "candidate_artifact_sha256": "c" * 64,
        "from_revision_ref": rev_a, "to_revision_ref": rev_b,
        "reason": "author accepted", "scope_verdict": "PASS",
        "decided_at": NOW, "does_not_prove": ["quality"]}, "decision"),
        ({"schema": "flywheel.writing-review/v1", "project_ref": PROJECT,
        "review_ref": wrev_a, "revision_refs": [rev_b],
        "reader_flow_ref": diag_a, "source_coverage": {"status": "checked",
        "basis": "deterministic", "measurement_status": "checked",
        "source_packet_ref": "packet_main", "diagnostic_ref": diag_a,
        "source_refs": ["src_receipt"]},
        "style_lint": {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_refs": []},
        "scope_preservation": {"status": "checked", "basis": "deterministic",
        "measurement_status": "checked", "decision_refs": [dec_a]},
        "quality_measurement": {"status": "unmeasured", "basis": "deterministic",
        "measurement_status": "unmeasured", "source_refs": []},
        "blocking_items": [], "does_not_prove": ["quality"]}, "review"),
        ({"schema": "flywheel.writing-export/v1", "project_ref": PROJECT,
        "export_ref": wexp_a, "manuscript_ref": "manuscript_a",
        "manuscript_sha256": "d" * 64,
        "included_sections": [{"section_ref": "sec_recommendation",
        "revision_ref": rev_b, "body_sha256": "b" * 64, "order_index": 0}],
        "decision_refs": [dec_a], "review_ref": wrev_a,
        "source_packet_ref": "packet_main", "journey_ref": "jrn_a",
        "event_head_sha256": "e" * 64, "does_not_prove": ["quality"]}, "export"),
    ]
    for artifact, kind in artifacts:
        assert validate_artifact(artifact, kind)["schema"] == artifact["schema"]
    with pytest.raises(WritingTypeError):
        validate_artifact({"schema": "flywheel.writing-section/v1",
            "project_ref": PROJECT, "section_ref": "sec_old",
            "label": "Old", "position": 0}, "section")
    with pytest.raises(WritingTypeError):
        validate_artifact({"schema": "flywheel.writing-card/v1",
            "project_ref": PROJECT, "card_ref": "card_old",
            "kind": "revise", "problem_summary": "old", "target": target,
            "reported_by": "fixture", "does_not_prove": ["quality"]}, "card")


def test_service_pipeline_persists_v2_review_export_bindings(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    init = service.prepare_init(_write(tmp_path / "brief.json", _brief()),
        _write(tmp_path / "sources.json", _source_packet()), client_request_id="init")
    ack = _flow(service, init)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    head = _flow(service, service.prepare_section(
        journey, head, _section(), client_request_id="section"))["event_head_sha256"]
    revision = service.prepare_revision(journey, head, PROJECT,
        "sec_recommendation", "Recommendation: hold.\n", client_request_id="rev")
    head = _flow(service, revision)["event_head_sha256"]
    diag = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag")
    diag_artifact = service.artifacts.read_json(
        diag["artifact_ref"], diag["artifact_sha256"], expected_kind="diagnostic")
    assert diag_artifact["schema"] == "flywheel.writing-reader-flow-diagnostic/v1"
    assert diag_artifact["reader_state_summary"]["measurement_status"] == "unmeasured"
    head = _flow(service, diag)["event_head_sha256"]
    card = {"schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT, "card_ref": "card_" + "c" * 32,
        "diagnostic_ref": diag_artifact["diagnostic_ref"], "target": _target(revision),
        "problem": "old recommendation", "goal": "switch to release",
        "must_preserve": ["outside target"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change evidence"], "source_refs": ["src_receipt"],
        "voice_constraints": "direct", "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(journey, head, PROJECT, "card_" + "c" * 32,
        "Recommendation: release.\n", client_request_id="candidate")
    cand_artifact = service.artifacts.read_json(
        candidate["artifact_ref"], candidate["artifact_sha256"], expected_kind="candidate")
    assert cand_artifact["base_revision_ref"] == revision["revision_ref"]
    assert cand_artifact["out_of_scope_changes"] == []
    head = _flow(service, candidate)["event_head_sha256"]
    accept = service.prepare_decision(journey, head, PROJECT, decision="accept",
        candidate_ref=candidate["candidate_ref"], client_request_id="accept")
    dec_artifact = service.artifacts.read_json(
        accept["artifact_ref"], accept["artifact_sha256"], expected_kind="decision")
    assert dec_artifact["scope_verdict"] == "PASS"
    head = _flow(service, accept)["event_head_sha256"]
    diag2 = service.prepare_diagnose(journey, head, PROJECT,
        cand_artifact["candidate_revision_ref"], client_request_id="diag2")
    diag2_artifact = service.artifacts.read_json(
        diag2["artifact_ref"], diag2["artifact_sha256"], expected_kind="diagnostic")
    head = _flow(service, diag2)["event_head_sha256"]
    review = service.prepare_review(journey, head, PROJECT, client_request_id="review")
    review_artifact = service.artifacts.read_json(
        review["artifact_ref"], review["artifact_sha256"], expected_kind="review")
    assert review_artifact["revision_refs"] == [cand_artifact["candidate_revision_ref"]]
    assert review_artifact["reader_flow_ref"] == diag2_artifact["diagnostic_ref"]
    head = _flow(service, review)["event_head_sha256"]
    export = service.prepare_export(journey, head, PROJECT,
        out_ref="article", client_request_id="export")
    export_artifact = service.artifacts.read_json(
        export["artifact_ref"], export["artifact_sha256"], expected_kind="export")
    assert export_artifact["review_ref"] == review_artifact["review_ref"]
    assert export_artifact["source_packet_ref"] == "packet_main"
    assert export_artifact["journey_ref"] == journey
    assert export_artifact["event_head_sha256"] == head


def test_reject_scope_hold_candidate_records_disposition_without_text_change(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    init = service.prepare_init(_write(tmp_path / "brief.json", _brief()),
        _write(tmp_path / "sources.json", _source_packet()), client_request_id="init")
    ack = _flow(service, init)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    head = _flow(service, service.prepare_section(
        journey, head, _section(), client_request_id="section"))["event_head_sha256"]
    base = "KEEP\nCHANGE\nKEEP\n"
    revision = service.prepare_revision(journey, head, PROJECT,
        "sec_recommendation", base, client_request_id="rev")
    head = _flow(service, revision)["event_head_sha256"]
    diag = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag-oos")
    diag_artifact = service.artifacts.read_json(
        diag["artifact_ref"], diag["artifact_sha256"], expected_kind="diagnostic")
    head = _flow(service, diag)["event_head_sha256"]
    target = {"section_ref": "sec_recommendation",
        "base_revision_ref": revision["revision_ref"],
        "base_body_sha256": revision["body_sha256"], "coordinate_type": "unicode_codepoint", "start": 5, "end": 11,
        "selected_span_sha256": sha256_bytes(b"CHANGE")}
    card = {"schema": "flywheel.writing-scoped-revision/v1",
        "project_ref": PROJECT, "card_ref": "card_" + "d" * 32,
        "diagnostic_ref": diag_artifact["diagnostic_ref"],
        "target": target, "problem": "change middle only",
        "goal": "reject out-of-scope candidate", "must_preserve": ["KEEP lines"],
        "allowed_operations": ["replace"], "forbidden_operations": ["change context"],
        "source_refs": ["src_receipt"], "voice_constraints": "direct",
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    candidate = service.prepare_candidate(journey, head, PROJECT, "card_" + "d" * 32,
        "OUTSIDE SCOPE\n", client_request_id="candidate")
    assert candidate["scope_verdict"] == "HOLD"
    head = _flow(service, candidate)["event_head_sha256"]
    reject = service.prepare_decision(journey, head, PROJECT, decision="reject",
        candidate_ref=candidate["candidate_ref"], client_request_id="reject")
    record = read_proposal_record(
        reject["proposal_ref"], owner_ref=service.owner_ref,
        state_root=service.state_root)
    result, status = journey_post("/api/journeys/append",
        canonical_bytes({**record["request"], "grant_ref":
        service.approve_proposal(reject["proposal_ref"])["grant_ref"]}),
        owner_ref=service.owner_ref, state_root=service.state_root,
        evidence_root=service.artifacts.root, clock=service.clock)
    assert status == 200
    state = service.project_state(journey)
    assert state["sections"]["sec_recommendation"]["current_body"] == base
    assert state["decisions"][-1]["decision"] == "reject"
    assert state["decisions"][-1]["scope_verdict"] == "HOLD"


def test_cli_proposal_get_returns_typed_json_on_body_drift(tmp_path):
    service = WritingService(tmp_path / "home", clock=lambda: NOW)
    init = service.prepare_init(_write(tmp_path / "brief.json", _brief()),
        _write(tmp_path / "sources.json", _source_packet()), client_request_id="init")
    ack = _flow(service, init)
    journey, head = ack["journey_ref"], ack["event_head_sha256"]
    head = _flow(service, service.prepare_section(
        journey, head, _section(), client_request_id="section"))["event_head_sha256"]
    proposal = service.prepare_revision(journey, head, PROJECT,
        "sec_recommendation", "Body before approval.\n", client_request_id="rev")
    record = read_proposal_record(
        proposal["proposal_ref"], owner_ref=service.owner_ref,
        state_root=service.state_root)
    artifact = service.artifacts.read_json(
        record["request"]["command"]["artifact_ref"],
        record["request"]["command"]["artifact_sha256"], expected_kind="revision")
    service.artifacts.path_for_ref(artifact["body_ref"]).write_text(
        "Body after approval.\n", encoding="utf-8")
    env = {**os.environ, "FLYWHEEL_HOME": str(tmp_path / "home"),
        "PYTHONPATH": os.getcwd()}
    run = subprocess.run([sys.executable, "-m", "harness.cli_entry",
        "writing", "proposal", "get", proposal["proposal_ref"], "--json"],
        cwd=os.getcwd(), env=env, capture_output=True, text=True)
    assert run.returncode != 0
    assert json.loads(run.stdout)["error"]["code"] == "ARTIFACT_DRIFT"
    assert "Traceback" not in run.stderr
