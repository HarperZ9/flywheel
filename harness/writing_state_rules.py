"""Shared Writing Workspace transition rules over projected state."""
from __future__ import annotations

from .writing_artifacts import WritingArtifactStore
from .writing_reader_flow import scope_replacement_plan
from .writing_state_authority import (
    WritingAuthorityError, check_diagnostic_marker_facts,
    check_problem_authority, check_review_measured, check_review_unmeasured,
    check_source_marker, check_summary_authority, check_unit_authority,
)
from .writing_types import (
    MAX_AUTHOR_TEXT_BYTES, MAX_MANUSCRIPT_TEXT_BYTES,
    MAX_SOURCE_PACKET_BYTES, sha256_bytes,
)


class WritingStateError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_transition(state: dict, kind: str, artifact: dict,
                        artifacts: WritingArtifactStore,
                        owner_ref: str | None) -> None:
    if kind == "section":
        if artifact["section_ref"] not in state["sections"] and len(state["sections"]) >= 8:
            raise WritingStateError("SECTION_LIMIT")
    elif kind == "revision":
        _validate_revision(state, artifact, artifacts, owner_ref)
    elif kind == "diagnostic":
        _validate_diagnostic(state, artifact, artifacts, owner_ref)
    elif kind == "card":
        _validate_card(state, artifact, artifacts, owner_ref)
    elif kind == "candidate":
        _validate_candidate(state, artifact, artifacts, owner_ref)
    elif kind == "decision":
        validate_decision(state, artifact)
    elif kind == "review":
        _validate_review(state, artifact, artifacts, owner_ref)
    elif kind == "export":
        _validate_export(state, artifact, artifacts, owner_ref)


def validate_decision(state: dict, decision: dict) -> None:
    section = state["sections"].get(decision["section_ref"])
    if section is None: raise WritingStateError("SECTION_NOT_FOUND")
    if section["current_revision_ref"] != decision["from_revision_ref"]:
        raise WritingStateError("HEAD_CONFLICT")
    accepted = state["accepted_revision_refs_by_section"].get(decision["section_ref"], [])
    if decision["decision"] == "rollback":
        if decision["to_revision_ref"] not in accepted:
            raise WritingStateError("ROLLBACK_TARGET_INVALID")
        return
    candidate = state["candidates"].get(decision["candidate_ref"])
    if candidate is None or decision["to_revision_ref"] != candidate["candidate_revision_ref"]:
        raise WritingStateError("CANDIDATE_NOT_FOUND")
    if (candidate.get("artifact_ref") != decision["candidate_artifact_ref"]
            or candidate.get("artifact_sha256") != decision["candidate_artifact_sha256"]):
        raise WritingStateError("CANDIDATE_ARTIFACT_MISMATCH")
    card = state["cards"].get(candidate["card_ref"]); target = card.get("target") if type(card) is dict else {}
    if (target.get("section_ref") != decision["section_ref"]
            or target.get("base_revision_ref") != decision["from_revision_ref"]
            or candidate["base_revision_ref"] != decision["from_revision_ref"]):
        raise WritingStateError("CANDIDATE_TARGET_MISMATCH")
    verdict = candidate["scope_receipt"].get("verdict")
    if decision["scope_verdict"] != verdict:
        raise WritingStateError("SCOPE_VERDICT_DRIFT")
    if decision["decision"] == "accept" and verdict != "PASS":
        raise WritingStateError("SCOPE_VIOLATION")


def _validate_revision(state: dict, revision: dict, artifacts: WritingArtifactStore,
                       owner_ref: str | None) -> None:
    section = state["sections"].get(revision["section_ref"])
    if section is None: raise WritingStateError("SECTION_NOT_FOUND")
    if section["current_revision_ref"] != revision["base_revision_ref"]:
        raise WritingStateError("HEAD_CONFLICT")
    _read_text(state, artifacts, owner_ref, revision["body_ref"], revision["body_sha256"])


def _validate_candidate(state: dict, candidate: dict,
                        artifacts: WritingArtifactStore,
                        owner_ref: str | None) -> None:
    card = state["cards"].get(candidate["card_ref"])
    if type(card) is not dict: raise WritingStateError("CARD_NOT_FOUND")
    if candidate["base_revision_ref"] != card["target"]["base_revision_ref"]:
        raise WritingStateError("CANDIDATE_TARGET_MISMATCH")
    base = _base_text(state, card["target"], artifacts, owner_ref)
    body = _read_text(state, artifacts, owner_ref,
        candidate["candidate_body_ref"], candidate["candidate_body_sha256"])
    receipt = scope_replacement_plan(base, body, card["target"])
    if receipt != candidate["scope_receipt"] or candidate["out_of_scope_changes"] != receipt["failure_reasons"]:
        raise WritingStateError("SCOPE_RECEIPT_DRIFT")


def _validate_diagnostic(state: dict, diagnostic: dict,
                         artifacts: WritingArtifactStore,
                         owner_ref: str | None) -> None:
    revision = state["revisions"].get(diagnostic["revision_ref"])
    if revision is None or revision["body_sha256"] != diagnostic["body_sha256"]:
        raise WritingStateError("REVISION_NOT_FOUND")
    body = _read_text(state, artifacts, owner_ref,
        revision["body_ref"], revision["body_sha256"])
    sources = set(_source_ids(state, artifacts, owner_ref))
    try:
        for item in [diagnostic["reader_state_summary"]]:
            _bind_authority(item, diagnostic, body, sources)
            check_summary_authority(item)
        for field in ("units", "problems", "source_grounding"):
            for item in diagnostic[field]:
                _bind_authority(item, diagnostic, body, sources)
                if field == "units":
                    _check_span(item["start"], item["end"], item["excerpt"], body)
                    check_unit_authority(item)
                elif field == "problems":
                    check_problem_authority(item, body, sources)
                else:
                    check_source_marker(item, body, sources)
        check_diagnostic_marker_facts(diagnostic, body, sources)
    except WritingAuthorityError as exc:
        raise WritingStateError(exc.code) from exc


def _validate_card(state: dict, card: dict, artifacts: WritingArtifactStore,
                   owner_ref: str | None) -> None:
    _base_text(state, card["target"], artifacts, owner_ref)
    diagnostic = state["diagnostics"].get(card["diagnostic_ref"])
    if (type(diagnostic) is not dict
            or diagnostic["revision_ref"] != card["target"]["base_revision_ref"]
            or diagnostic["body_sha256"] != card["target"]["base_body_sha256"]):
        raise WritingStateError("DIAGNOSTIC_REF_INVALID")
    sources = set(_source_ids(state, artifacts, owner_ref))
    if any(source not in sources for source in card["source_refs"]):
        raise WritingStateError("SOURCE_REF_INVALID")


def _validate_review(state: dict, review: dict, artifacts: WritingArtifactStore,
                     owner_ref: str | None) -> None:
    if review["revision_refs"] != _current_revision_refs(state):
        raise WritingStateError("REVIEW_HEAD_MISMATCH")
    flow = review["reader_flow_ref"]
    latest = _latest_ref(state["diagnostics"], "diag_unmeasured")
    decisions = [row["decision_ref"] for row in state["decisions"]]
    sources = set(_source_ids(state, artifacts, owner_ref))
    if review["source_coverage"]["source_packet_ref"] != _source_packet_ref(state, artifacts, owner_ref):
        raise WritingStateError("REVIEW_SOURCE_MISMATCH")
    if flow == "diag_unmeasured":
        try:
            check_review_unmeasured(review, decisions)
        except WritingAuthorityError as exc:
            raise WritingStateError(exc.code) from exc
        return
    diagnostic = state["diagnostics"].get(flow)
    if flow != latest or type(diagnostic) is not dict or diagnostic["revision_ref"] not in review["revision_refs"]:
        raise WritingStateError("REVIEW_READER_FLOW_MISMATCH")
    if review["source_coverage"]["diagnostic_ref"] != flow:
        raise WritingStateError("REVIEW_SOURCE_MISMATCH")
    if any(source not in sources for source in review["source_coverage"]["source_refs"]):
        raise WritingStateError("SOURCE_REF_INVALID")
    try:
        check_review_measured(review, diagnostic)
    except WritingAuthorityError as exc:
        raise WritingStateError(exc.code) from exc
    if review["scope_preservation"]["decision_refs"] != decisions:
        raise WritingStateError("REVIEW_SCOPE_MISMATCH")


def _validate_export(state: dict, export: dict, artifacts: WritingArtifactStore,
                     owner_ref: str | None) -> None:
    if export["included_sections"] != _included_sections(state):
        raise WritingStateError("EXPORT_HEAD_MISMATCH")
    if export["decision_refs"] != [row["decision_ref"] for row in state["decisions"]]:
        raise WritingStateError("EXPORT_DECISION_MISMATCH")
    if export["review_ref"] != _latest_ref({row["review_ref"]: row for row in state["reviews"]}, "wrev_unmeasured"):
        raise WritingStateError("EXPORT_REVIEW_MISMATCH")
    if export["source_packet_ref"] != _source_packet_ref(state, artifacts, owner_ref):
        raise WritingStateError("EXPORT_SOURCE_MISMATCH")
    if export["journey_ref"] != state["journey_ref"] or export["event_head_sha256"] != state["event_head_sha256"]:
        raise WritingStateError("EXPORT_HEAD_MISMATCH")
    expected = "\n".join(_section_current_body(state, artifacts, owner_ref, name) for name in state["section_order"])
    actual = _read_text(state, artifacts, owner_ref,
        export["manuscript_ref"], export["manuscript_sha256"],
        max_bytes=MAX_MANUSCRIPT_TEXT_BYTES)
    if actual != expected: raise WritingStateError("EXPORT_MANUSCRIPT_MISMATCH")


def _base_text(state: dict, target: dict, artifacts: WritingArtifactStore,
               owner_ref: str | None) -> str:
    revision = state["revisions"].get(target["base_revision_ref"])
    if revision is None or revision["section_ref"] != target["section_ref"]:
        raise WritingStateError("REVISION_NOT_FOUND")
    return _read_text(state, artifacts, owner_ref, revision["body_ref"], revision["body_sha256"])


def _source_packet_ref(state: dict, artifacts: WritingArtifactStore, owner_ref: str | None) -> str:
    intake = state["intake"]
    packet = artifacts.read_json(intake["source_packet_ref"],
        intake["source_packet_sha256"], expected_kind="source_packet",
        max_bytes=MAX_SOURCE_PACKET_BYTES, expected_owner_ref=owner_ref,
        expected_project_ref=state["project_ref"])
    return packet.get("source_packet_ref") or intake["source_packet_ref"]


def _source_ids(state: dict, artifacts: WritingArtifactStore,
                owner_ref: str | None) -> list[str]:
    intake = state["intake"]
    packet = artifacts.read_json(intake["source_packet_ref"],
        intake["source_packet_sha256"], expected_kind="source_packet",
        max_bytes=MAX_SOURCE_PACKET_BYTES, expected_owner_ref=owner_ref,
        expected_project_ref=state["project_ref"])
    return [source["source_id"] for source in packet["sources"]]


def _current_revision_refs(state: dict) -> list[str]:
    return [state["sections"][name]["current_revision_ref"] for name in state["section_order"] if state["sections"][name].get("current_revision_ref")]


def _included_sections(state: dict) -> list[dict]:
    return [{"section_ref": name, "revision_ref": state["sections"][name]["current_revision_ref"],
        "body_sha256": state["sections"][name]["current_body_sha256"],
        "order_index": state["sections"][name]["order_index"]}
        for name in state["section_order"] if state["sections"][name].get("current_revision_ref")]


def _latest_ref(rows: dict, missing: str) -> str:
    return next(reversed(rows), missing)


def _section_current_body(state: dict, artifacts: WritingArtifactStore,
                          owner_ref: str | None, section_ref: str) -> str:
    section = state["sections"][section_ref]
    return _read_text(state, artifacts, owner_ref,
        section["current_body_ref"], section["current_body_sha256"])


def _read_text(state: dict, artifacts: WritingArtifactStore,
               owner_ref: str | None, ref: str, digest: str,
               *, max_bytes: int | None = None) -> str:
    return artifacts.read_text(ref, digest, expected_owner_ref=owner_ref,
        expected_project_ref=state["project_ref"],
        max_bytes=max_bytes or MAX_AUTHOR_TEXT_BYTES)


def _bind_authority(item: dict, diagnostic: dict, body: str, sources: set[str]) -> None:
    if (item["base_revision_ref"] != diagnostic["revision_ref"]
            or item["base_body_sha256"] != diagnostic["body_sha256"]):
        raise WritingStateError("DIAGNOSTIC_BODY_MISMATCH")
    if any(source not in sources for source in item["source_refs"]):
        raise WritingStateError("SOURCE_REF_INVALID")
    for span in item["span_refs"]:
        _check_span(span["start"], span["end"], span["excerpt"], body,
                    span["span_sha256"])


def _check_span(start: int, end: int, excerpt: str, body: str,
                digest: str | None = None) -> None:
    if end > len(body) or body[start:end] != excerpt:
        raise WritingStateError("DIAGNOSTIC_BODY_MISMATCH")
    if digest and sha256_bytes(excerpt.encode("utf-8")) != digest:
        raise WritingStateError("DIAGNOSTIC_BODY_MISMATCH")
