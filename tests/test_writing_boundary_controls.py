import json
import os
import subprocess
import sys

import pytest

from harness.evidence_json import canonical_bytes
from harness.grant_route import read_proposal_record
from harness.journey_route import journey_post
from harness.writing_service import WritingError, WritingService
from harness.writing_types import WRITING_DOES_NOT_PROVE, sha256_bytes


NOW = "2026-09-08T12:00:00Z"
PROJECT = "wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CARD = "card_" + "1" * 32


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
    brief = _json(tmp_path / "brief.json", {"schema": "flywheel.writing-project-brief/v1",
        "project_ref": PROJECT, "mode": "nonfiction", "form": "essay",
        "working_title": "Boundary controls", "audience": "operators",
        "reader_job": "verify custody", "author_intent": "repair boundary controls",
        "voice_contract": {"style_ref": "voice_rules"},
        "source_packet_ref": "packet_main", "writing_profile": "nonfiction",
        "does_not_prove": ["truth"]})
    sources = _json(tmp_path / "sources.json", {"schema": "flywheel.writing-source-packet/v1",
        "project_ref": PROJECT, "source_packet_ref": "packet_main",
        "sources": [{"source_id": "src_one", "title": "Receipt",
        "origin": "local", "allowed_use": "cite"}],
        "does_not_prove": ["interpretation"]})
    ack = _flow(service, service.prepare_init(brief, sources, client_request_id="init"))
    return service, ack["journey_ref"], ack["event_head_sha256"]


def _section(service, journey, head, ref, position):
    section = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": ref, "heading": ref, "purpose": "record a section",
        "reader_entry_state": "unknown", "promises": ["draft remains private"],
        "order_index": position}
    return _flow(service, service.prepare_section(
        journey, head, section, client_request_id=f"section-{position}"))["event_head_sha256"]


def _revision(service, journey, head, body, request_id):
    proposal = service.prepare_revision(
        journey, head, PROJECT, "sec_one", body, client_request_id=request_id)
    return _flow(service, proposal)["event_head_sha256"], proposal


def _diagnose(service, journey, head, revision):
    proposal = service.prepare_diagnose(journey, head, PROJECT,
        revision["revision_ref"], client_request_id="diag-" + revision["revision_ref"][-6:])
    artifact = service.artifacts.read_json(
        proposal["artifact_ref"], proposal["artifact_sha256"], expected_kind="diagnostic")
    return _flow(service, proposal)["event_head_sha256"], artifact


def test_generic_revision_commit_revalidates_referenced_body(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    head, _ = _revision(service, journey, head, "one\n", "rev-one")
    proposal = service.prepare_revision(
        journey, head, PROJECT, "sec_one", "two\n", client_request_id="rev-two")
    record = read_proposal_record(
        proposal["proposal_ref"], owner_ref=service.owner_ref,
        state_root=service.state_root)
    artifact = service.artifacts.read_json(
        record["request"]["command"]["artifact_ref"],
        record["request"]["command"]["artifact_sha256"], expected_kind="revision")
    service.artifacts.path_for_ref(artifact["body_ref"]).write_text(
        "tampered\n", encoding="utf-8")

    result, status = _raw_commit(service, proposal)

    assert status == 403
    assert result["error"]["code"] == "ARTIFACT_DRIFT"


def test_raw_candidate_fabricated_scope_pass_is_recomputed(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    base = "KEEP\nCHANGE\nKEEP\n"
    head, revision = _revision(service, journey, head, base, "base")
    head, diagnostic = _diagnose(service, journey, head, revision)
    card = {"schema": "flywheel.writing-scoped-revision/v1", "project_ref": PROJECT,
        "card_ref": CARD, "diagnostic_ref": diagnostic["diagnostic_ref"],
        "problem": "Change middle only.", "goal": "replace selected text",
        "must_preserve": ["KEEP lines"], "allowed_operations": ["replace"],
        "forbidden_operations": ["change context"], "source_refs": ["src_one"],
        "voice_constraints": "direct", "target": {"section_ref": "sec_one",
        "base_revision_ref": revision["revision_ref"], "base_body_sha256": revision["body_sha256"],
        "coordinate_type": "unicode_codepoint",
        "start": 5, "end": 11, "selected_span_sha256": sha256_bytes(b"CHANGE")},
        "does_not_prove": ["quality"]}
    head = _flow(service, service.prepare_card(
        journey, head, card, client_request_id="card"))["event_head_sha256"]
    body = service.artifacts.write_text(
        service.owner_ref, PROJECT, "body", "fake_scope", "OUTSIDE SCOPE\n")
    fake = {"schema": "flywheel.writing-revision-candidate/v1", "project_ref": PROJECT,
        "candidate_ref": "cand_" + "f" * 32, "card_ref": CARD,
        "base_revision_ref": revision["revision_ref"],
        "candidate_revision_ref": "rev_" + "f" * 32, "candidate_body_ref": body["artifact_ref"],
        "candidate_body_sha256": body["artifact_sha256"],
        "diff_summary": "forged out-of-scope body", "out_of_scope_changes": [],
        "created_by": "fixture", "text_admission": body["text_admission"],
        "scope_receipt": {"verdict": "PASS", "failure_reasons": [], "target": card["target"],
        "replacement_text": "OUTSIDE SCOPE\n", "does_not_prove": WRITING_DOES_NOT_PROVE},
        "does_not_prove": [WRITING_DOES_NOT_PROVE]}
    proposal = service._prepare_artifact(
        journey, head, "fake-candidate", "candidate", "cand_" + "f" * 32, fake)

    result, status = _raw_commit(service, proposal)

    assert status == 403
    assert result["error"]["code"] == "SCOPE_RECEIPT_DRIFT"


def test_raw_section_append_enforces_section_cap(tmp_path):
    service, journey, head = _project(tmp_path)
    for index in range(8):
        head = _section(service, journey, head, f"sec_{index}", index)
    ninth = {"schema": "flywheel.writing-section/v1", "project_ref": PROJECT,
        "section_ref": "sec_ninth", "heading": "ninth", "purpose": "overflow",
        "reader_entry_state": "unknown", "promises": ["none"], "order_index": 9}
    with pytest.raises(WritingError, match="SECTION_LIMIT"):
        service.prepare_section(journey, head, ninth, client_request_id="ninth-normal")
    proposal = service._prepare_artifact(
        journey, head, "ninth-raw", "section", "sec_ninth", ninth)

    result, status = _raw_commit(service, proposal)

    assert status == 403
    assert result["error"]["code"] == "SECTION_LIMIT"


def test_same_text_and_restored_text_manual_saves_keep_lineage(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    head, first = _revision(service, journey, head, "FIRST\n", "first")
    head, second = _revision(service, journey, head, "SECOND\n", "second")
    head, same = _revision(service, journey, head, "SECOND\n", "second-again")
    _, restored = _revision(service, journey, head, "FIRST\n", "restored")
    state = WritingService(tmp_path / "home", clock=lambda: NOW).project_state(journey)

    assert len({first["revision_ref"], second["revision_ref"],
                same["revision_ref"], restored["revision_ref"]}) == 4
    assert state["sections"]["sec_one"]["current_body"] == "FIRST\n"
    assert state["revisions"][same["revision_ref"]]["base_revision_ref"] == second["revision_ref"]


def test_cli_status_returns_json_error_after_historical_body_drift(tmp_path):
    service, journey, head = _project(tmp_path)
    head = _section(service, journey, head, "sec_one", 1)
    _, revision = _revision(service, journey, head, "one\n", "one")
    artifact = service.artifacts.read_json(
        revision["artifact_ref"], revision["artifact_sha256"], expected_kind="revision")
    service.artifacts.path_for_ref(artifact["body_ref"]).write_text(
        "changed\n", encoding="utf-8")
    env = {**os.environ, "FLYWHEEL_HOME": str(tmp_path / "home"),
           "PYTHONPATH": str(os.getcwd())}
    run = subprocess.run([sys.executable, "-m", "harness.cli_entry",
        "writing", "status", "--json"], cwd=os.getcwd(), env=env,
        capture_output=True, text=True)

    assert run.returncode != 0
    assert json.loads(run.stdout)["error"]["code"] == "ARTIFACT_DRIFT"
    assert "Traceback" not in run.stderr
