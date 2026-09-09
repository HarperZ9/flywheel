"""Strict stdlib types for the private Writing Workspace workflow."""
from __future__ import annotations
import hashlib
import re
from copy import deepcopy
from typing import Any
from .evidence_json import canonical_bytes
from .evidence_public import TransportError, public_metadata
from .writing_authority_schema import (AUTHORITY_FIELDS, admit_text as _admit_text, authority_shape_error, authority_tuple_error, review_result_shape_error, text_admission_error)
MAX_AUTHOR_TEXT_BYTES = 262_144
MAX_BRIEF_JSON_BYTES = 65_536
MAX_ARTIFACT_JSON_BYTES = 262_144
MAX_SOURCE_PACKET_BYTES = 1_048_576
MAX_MANUSCRIPT_TEXT_BYTES = 1_048_576
WRITING_DOES_NOT_PROVE = ("this writing artifact does not prove prose quality, factual truth, "
    "source completeness, or publication readiness")
OWNER_PATTERN = re.compile(r"owner_[0-9a-f]{32}\Z")
PROJECT_PATTERN = re.compile(r"wpr_[0-9a-f]{32}\Z")
SAFE_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
OPAQUE_PATTERNS = {k: re.compile(v) for k, v in {"section": r"sec_[a-z0-9][a-z0-9_-]{0,63}\Z", "revision": r"rev_[0-9a-f]{32}\Z", "diagnostic": r"diag_[0-9a-f]{32}\Z", "card": r"card_[0-9a-f]{32}\Z", "candidate": r"cand_[0-9a-f]{32}\Z", "decision": r"dec_[0-9a-f]{32}\Z", "review": r"wrev_[0-9a-f]{32}\Z", "export": r"wexp_[0-9a-f]{32}\Z"}.items()}
SCHEMAS = {"brief": "flywheel.writing-project-brief/v1",
    "source_packet": "flywheel.writing-source-packet/v1", "section":
    "flywheel.writing-section/v1", "revision": "flywheel.writing-revision/v1",
    "diagnostic": "flywheel.writing-reader-flow-diagnostic/v1", "card":
    "flywheel.writing-scoped-revision/v1", "candidate":
    "flywheel.writing-revision-candidate/v1", "decision":
    "flywheel.writing-decision/v1", "review": "flywheel.writing-review/v1",
    "export": "flywheel.writing-export/v1"}
KIND_BY_SCHEMA = {value: key for key, value in SCHEMAS.items()}
class WritingTypeError(ValueError): pass
def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
def canonical_digest(value: object) -> tuple[bytes, str]:
    raw = canonical_bytes(value)
    return raw, sha256_bytes(raw)
def admit_text(raw: str | bytes, *, max_bytes: int = MAX_AUTHOR_TEXT_BYTES) -> tuple[str, bytes, dict]:
    try:
        return _admit_text(raw, max_bytes=max_bytes)
    except ValueError as exc:
        raise WritingTypeError(str(exc)) from exc
def normalize_text(raw: str | bytes, *, max_bytes: int = MAX_AUTHOR_TEXT_BYTES) -> tuple[str, bytes]:
    text, data, _receipt = admit_text(raw, max_bytes=max_bytes)
    return text, data
def require_ref(value: object, field: str, prefix: str | None = None) -> str:
    if type(value) is not str:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    pattern = {
        "owner_": OWNER_PATTERN,
        "wpr_": PROJECT_PATTERN,
    }.get(prefix)
    if pattern is not None and pattern.fullmatch(value) is None:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    if pattern is None and SAFE_ID_PATTERN.fullmatch(value) is None:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    return value
def require_opaque(value: object, kind: str, field: str) -> str:
    if type(value) is not str or OPAQUE_PATTERNS[kind].fullmatch(value) is None:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    return value
def require_sha(value: object, field: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    return value
def require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise WritingTypeError(f"{field.upper()}_INVALID")
    try:
        public_metadata(value)
    except TransportError as exc:
        raise WritingTypeError("UNSAFE_METADATA") from exc
    return value
def require_string_list(value: object, field: str) -> list[str]:
    if type(value) is not list or not all(type(item) is str and item.strip() for item in value):
        raise WritingTypeError(f"{field.upper()}_INVALID")
    return list(value)
def require_non_bool_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise WritingTypeError(f"{field.upper()}_INVALID")
    return value
def validate_target(value: object, *, body: str | None = None) -> dict:
    if type(value) is not dict:
        raise WritingTypeError("TARGET_INVALID")
    target = dict(value)
    try:
        _exact(target, {"section_ref", "base_revision_ref", "base_body_sha256",
            "coordinate_type", "start", "end", "selected_span_sha256"})
    except WritingTypeError as exc:
        raise WritingTypeError("TARGET_INVALID") from exc
    if target.get("coordinate_type") != "unicode_codepoint":
        raise WritingTypeError("TARGET_COORDINATE_INVALID")
    require_opaque(target.get("section_ref"), "section", "section_ref")
    require_opaque(target.get("base_revision_ref"), "revision", "base_revision_ref")
    require_sha(target.get("base_body_sha256"), "base_body_sha256")
    require_sha(target.get("selected_span_sha256"), "selected_span_sha256")
    start = require_non_bool_int(target.get("start"), "start")
    end = require_non_bool_int(target.get("end"), "end")
    if end <= start:
        raise WritingTypeError("TARGET_RANGE_INVALID")
    if body is not None:
        if end > len(body):
            raise WritingTypeError("TARGET_RANGE_INVALID")
        selected = body[start:end]
        if sha256_bytes(selected.encode("utf-8")) != target["selected_span_sha256"]:
            raise WritingTypeError("TARGET_SPAN_DRIFT")
    return target
def validate_artifact(value: object, expected_kind: str | None = None) -> dict:
    if type(value) is not dict:
        raise WritingTypeError("ARTIFACT_INVALID")
    artifact = deepcopy(value)
    schema = artifact.get("schema")
    kind = KIND_BY_SCHEMA.get(schema)
    if kind is None or (expected_kind is not None and kind != expected_kind):
        raise WritingTypeError("ARTIFACT_SCHEMA_INVALID")
    try:
        public_metadata(_public_shape(artifact))
    except TransportError as exc:
        raise WritingTypeError("UNSAFE_METADATA") from exc
    project_ref = require_ref(artifact.get("project_ref"), "project_ref", "wpr_")
    validators = {
        "brief": _validate_brief,
        "source_packet": _validate_source_packet,
        "section": _validate_section,
        "revision": _validate_revision,
        "diagnostic": _validate_diagnostic,
        "card": _validate_card,
        "candidate": _validate_candidate,
        "decision": _validate_decision,
        "review": _validate_review,
        "export": _validate_export,
    }
    validators[kind](artifact)
    artifact["project_ref"] = project_ref
    return artifact
def _public_shape(value: Any) -> Any:
    if type(value) is dict:
        safe = {}
        for key, item in value.items():
            if item is None:
                safe[key] = "null"
            elif key == "span_refs":
                safe[key] = ["span_ref" for _ in item] if type(item) is list else "span_ref"
            elif key in {"body", "author_intent", "problem", "goal", "audience", "heading", "purpose", "reader_entry_state", "excerpt", "comment"}:
                safe[key] = "private"
            else:
                safe[key] = _public_shape(item)
        return safe
    if type(value) is list:
        return [_public_shape(item) for item in value]
    return value
def _validate_refs(value: object, field: str) -> None:
    if type(value) is str:
        require_text(value, field)
    elif type(value) is dict:
        for key in value:
            require_ref(key, field)
        public_metadata(value)
    elif type(value) is list and all(type(item) is str and item.strip() for item in value):
        public_metadata(value)
    else:
        raise WritingTypeError(f"{field.upper()}_INVALID")
def _validate_brief(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "mode", "form", "working_title", "audience", "reader_job", "author_intent", "voice_contract", "source_packet_ref", "writing_profile", "does_not_prove"})
    if require_text(value.get("mode"), "mode") != "nonfiction": raise WritingTypeError("UNSUPPORTED_WRITING_MODE")
    if require_text(value.get("form"), "form") not in {"editorial", "blog", "essay"}: raise WritingTypeError("UNSUPPORTED_WRITING_FORM")
    for field in ("working_title", "audience", "reader_job", "author_intent", "source_packet_ref", "writing_profile"): require_text(value.get(field), field)
    _validate_refs(value["voice_contract"], "voice_contract"); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_source_packet(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "source_packet_ref", "sources", "does_not_prove"})
    require_text(value["source_packet_ref"], "source_packet_ref")
    sources = value.get("sources")
    if type(sources) is not list or not sources or len(sources) > 32: raise WritingTypeError("SOURCES_INVALID")
    for source in sources:
        if type(source) is not dict: raise WritingTypeError("SOURCES_INVALID")
        required, optional = {"source_id", "title", "origin", "allowed_use"}, {"body_ref", "body_sha256"}
        if not required.issubset(source) or set(source) - required - optional: raise WritingTypeError("SOURCES_INVALID")
        for field in required | (set(source) & {"body_ref"}): require_text(source.get(field), field)
        if "body_sha256" in source: require_sha(source.get("body_sha256"), "body_sha256")
    require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_section(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "section_ref", "heading", "purpose", "reader_entry_state", "promises", "order_index"})
    require_opaque(value.get("section_ref"), "section", "section_ref"); require_text(value.get("heading"), "heading")
    require_text(value.get("purpose"), "purpose"); require_text(value.get("reader_entry_state"), "reader_entry_state")
    require_string_list(value.get("promises"), "promises"); require_non_bool_int(value.get("order_index"), "order_index")
def _validate_revision(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "section_ref", "revision_ref", "base_revision_ref", "body_ref", "body_sha256", "word_count", "author_supplied", "scope_refs", "text_admission", "does_not_prove"})
    require_opaque(value.get("section_ref"), "section", "section_ref"); require_opaque(value.get("revision_ref"), "revision", "revision_ref")
    if value.get("base_revision_ref") is not None: require_opaque(value.get("base_revision_ref"), "revision", "base_revision_ref")
    require_text(value.get("body_ref"), "body_ref"); require_sha(value.get("body_sha256"), "body_sha256")
    require_non_bool_int(value.get("word_count"), "word_count")
    if type(value.get("author_supplied")) is not bool: raise WritingTypeError("AUTHOR_SUPPLIED_INVALID")
    require_string_list(value.get("scope_refs"), "scope_refs"); _validate_text_admission(value.get("text_admission"), value["body_sha256"]); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_diagnostic(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "diagnostic_ref", "revision_ref", "body_sha256", "reader_state_summary", "units", "problems", "revision_cards", "source_grounding", "does_not_prove"})
    require_opaque(value.get("diagnostic_ref"), "diagnostic", "diagnostic_ref"); require_opaque(value.get("revision_ref"), "revision", "revision_ref"); require_sha(value.get("body_sha256"), "body_sha256")
    summary = value.get("reader_state_summary")
    if type(summary) is not dict: raise WritingTypeError("READER_STATE_SUMMARY_INVALID")
    _authority_shape(summary, "reader_state_summary", {"entry_state", "new_information", "exit_state"})
    if not all(type(summary.get(field)) is str for field in ("entry_state", "exit_state")): raise WritingTypeError("READER_STATE_SUMMARY_INVALID")
    if type(summary.get("new_information")) is not list or not all(type(item) is str for item in summary["new_information"]): raise WritingTypeError("READER_STATE_SUMMARY_INVALID")
    _authority(summary, "reader_state_summary"); _validate_units(value.get("units")); _validate_problem_list(value.get("problems"), "problems")
    for card in _dict_list(value.get("revision_cards"), "revision_cards"): _validate_card_fields(card, require_diag=False)
    _validate_problem_list(value.get("source_grounding"), "source_grounding"); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_card(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "card_ref", "diagnostic_ref", "target", "problem", "goal", "must_preserve", "allowed_operations", "forbidden_operations", "source_refs", "voice_constraints", "does_not_prove"})
    _validate_card_fields(value, require_diag=True); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_candidate(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "candidate_ref", "card_ref", "base_revision_ref", "candidate_revision_ref", "candidate_body_ref", "candidate_body_sha256", "diff_summary", "out_of_scope_changes", "created_by", "scope_receipt", "text_admission", "does_not_prove"})
    require_opaque(value.get("candidate_ref"), "candidate", "candidate_ref"); require_opaque(value.get("card_ref"), "card", "card_ref"); require_opaque(value.get("base_revision_ref"), "revision", "base_revision_ref"); require_opaque(value.get("candidate_revision_ref"), "revision", "candidate_revision_ref")
    require_text(value.get("candidate_body_ref"), "candidate_body_ref"); require_sha(value.get("candidate_body_sha256"), "candidate_body_sha256"); require_text(value.get("diff_summary"), "diff_summary"); require_string_list(value.get("out_of_scope_changes"), "out_of_scope_changes"); require_text(value.get("created_by"), "created_by")
    _validate_text_admission(value.get("text_admission"), value["candidate_body_sha256"])
    receipt = value.get("scope_receipt")
    if type(receipt) is not dict or receipt.get("verdict") not in {"PASS", "HOLD"}: raise WritingTypeError("SCOPE_RECEIPT_INVALID")
    require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_decision(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "decision_ref", "decision", "section_ref", "candidate_ref", "candidate_artifact_ref", "candidate_artifact_sha256", "from_revision_ref", "to_revision_ref", "reason", "scope_verdict", "decided_at", "does_not_prove"})
    require_opaque(value.get("decision_ref"), "decision", "decision_ref")
    if value.get("decision") not in {"accept", "reject", "supersede", "rollback"}: raise WritingTypeError("DECISION_INVALID")
    require_opaque(value.get("section_ref"), "section", "section_ref"); require_text(value.get("reason"), "reason"); require_text(value.get("decided_at"), "decided_at")
    if value.get("scope_verdict") not in {"PASS", "HOLD", "NOT_APPLICABLE"}: raise WritingTypeError("SCOPE_VERDICT_INVALID")
    if value.get("candidate_ref") is not None: require_opaque(value.get("candidate_ref"), "candidate", "candidate_ref"); require_text(value.get("candidate_artifact_ref"), "candidate_artifact_ref"); require_sha(value.get("candidate_artifact_sha256"), "candidate_artifact_sha256")
    if value.get("from_revision_ref") is not None: require_opaque(value.get("from_revision_ref"), "revision", "from_revision_ref")
    if value.get("to_revision_ref") is not None: require_opaque(value.get("to_revision_ref"), "revision", "to_revision_ref")
    require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_review(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "review_ref", "revision_refs", "reader_flow_ref", "source_coverage", "style_lint", "scope_preservation", "quality_measurement", "blocking_items", "does_not_prove"})
    require_opaque(value.get("review_ref"), "review", "review_ref")
    refs = require_string_list(value.get("revision_refs"), "revision_refs")
    for ref in refs: require_opaque(ref, "revision", "revision_refs")
    flow = value.get("reader_flow_ref")
    if flow != "diag_unmeasured": require_opaque(flow, "diagnostic", "reader_flow_ref")
    _review_source(value.get("source_coverage")); _review_result(value.get("style_lint"), "style_lint", {"source_refs"})
    _review_result(value.get("scope_preservation"), "scope_preservation", {"decision_refs"})
    _review_result(value.get("quality_measurement"), "quality_measurement", {"source_refs"})
    if value["quality_measurement"].get("status") != "unmeasured": raise WritingTypeError("QUALITY_MEASUREMENT_INVALID")
    _validate_problem_list(value.get("blocking_items"), "blocking_items"); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_export(value: dict) -> None:
    _exact(value, {"schema", "project_ref", "export_ref", "manuscript_ref", "manuscript_sha256", "included_sections", "decision_refs", "review_ref", "source_packet_ref", "journey_ref", "event_head_sha256", "does_not_prove"})
    require_opaque(value.get("export_ref"), "export", "export_ref"); require_text(value.get("manuscript_ref"), "manuscript_ref"); require_sha(value.get("manuscript_sha256"), "manuscript_sha256")
    for section in _dict_list(value.get("included_sections"), "included_sections"):
        _exact(section, {"section_ref", "revision_ref", "body_sha256", "order_index"}); require_opaque(section["section_ref"], "section", "section_ref"); require_opaque(section["revision_ref"], "revision", "revision_ref"); require_sha(section["body_sha256"], "body_sha256"); require_non_bool_int(section["order_index"], "order_index")
    for ref in require_string_list(value.get("decision_refs"), "decision_refs"): require_opaque(ref, "decision", "decision_refs")
    require_opaque(value.get("review_ref"), "review", "review_ref") if value.get("review_ref") != "wrev_unmeasured" else None
    require_text(value.get("source_packet_ref"), "source_packet_ref"); require_ref(value.get("journey_ref"), "journey_ref"); require_sha(value.get("event_head_sha256"), "event_head_sha256"); require_string_list(value.get("does_not_prove"), "does_not_prove")
def _validate_card_fields(value: dict, *, require_diag: bool) -> None:
    require_opaque(value.get("card_ref"), "card", "card_ref")
    if require_diag: require_opaque(value.get("diagnostic_ref"), "diagnostic", "diagnostic_ref")
    validate_target(value.get("target")); require_text(value.get("problem"), "problem"); require_text(value.get("goal"), "goal"); require_string_list(value.get("must_preserve"), "must_preserve"); require_string_list(value.get("allowed_operations"), "allowed_operations"); require_string_list(value.get("forbidden_operations"), "forbidden_operations"); require_string_list(value.get("source_refs"), "source_refs"); require_text(value.get("voice_constraints"), "voice_constraints")
def _validate_units(value: object) -> None:
    units = _dict_list(value, "units")
    if len(units) > 256: raise WritingTypeError("UNITS_INVALID")
    for unit in units:
        _authority_shape(unit, "units", {"unit_ref", "start", "end", "excerpt",
            "topic_anchor", "comment", "handoff_to_next", "pattern",
            "heuristic_strength"})
        require_ref(unit["unit_ref"], "unit_ref"); require_text(unit["kind"], "kind"); start = require_non_bool_int(unit["start"], "start"); end = require_non_bool_int(unit["end"], "end")
        if end <= start or len(unit.get("excerpt", "")) > 160 or unit.get("pattern") not in {"anchored", "linking", "cathedral", "theme_preview", "mixed", "unclear"}: raise WritingTypeError("UNITS_INVALID")
        for field in ("excerpt", "topic_anchor", "comment", "handoff_to_next", "heuristic_strength"): require_text(unit.get(field), field)
        _authority(unit, "units")
def _validate_problem_list(value: object, field: str) -> None:
    for item in _dict_list(value, field):
        _authority_shape(item, field, {"status", "message", "source_id"})
        if "kind" in item and item["kind"] not in {"reader_state_summary", "source_marker", "stagnant_anchor", "missing_handoff", "unsupported_jump", "preview_without_followthrough", "claim_before_context", "citation_gap", "formulaic_pattern_risk", "unknown_source", "unchecked", "none"}: raise WritingTypeError(f"{field.upper()}_INVALID")
        if "message" in item: require_text(item["message"], "message")
        if "source_id" in item: require_ref(item["source_id"], "source_id")
        if "status" in item: require_text(item["status"], "status")
        _authority(item, field); public_metadata(_public_shape(item))
def _authority_shape(item: object, field: str, extra: set[str]) -> None:
    if code := authority_shape_error(item, extra, field):
        raise WritingTypeError(code)
def _authority(item: dict, field: str) -> None:
    if code := authority_tuple_error(item, field):
        raise WritingTypeError(code)
    require_opaque(item.get("base_revision_ref"), "revision", "base_revision_ref"); require_sha(item.get("base_body_sha256"), "base_body_sha256")
    for ref in require_string_list(item.get("source_refs"), "source_refs"): require_ref(ref, "source_ref")
    for span in _dict_list(item.get("span_refs"), "span_refs"):
        _exact(span, {"start", "end", "excerpt", "span_sha256"})
        start = require_non_bool_int(span.get("start"), "start"); end = require_non_bool_int(span.get("end"), "end")
        if end <= start or type(span.get("excerpt")) is not str or len(span["excerpt"]) > 160: raise WritingTypeError(f"{field.upper()}_SPAN_INVALID")
        require_sha(span.get("span_sha256"), "span_sha256")
def _review_result(value: object, field: str, extra: set[str]) -> None:
    if code := review_result_shape_error(value, extra, field):
        raise WritingTypeError(code)
    if "source_refs" in extra: require_string_list(value.get("source_refs"), "source_refs")
    if "decision_refs" in extra:
        for ref in require_string_list(value.get("decision_refs"), "decision_refs"): require_opaque(ref, "decision", "decision_refs")
def _review_source(value: object) -> None:
    _review_result(value, "source_coverage", {"source_packet_ref", "diagnostic_ref", "source_refs"})
    require_text(value.get("source_packet_ref"), "source_packet_ref")
    if value.get("diagnostic_ref") != "diag_unmeasured": require_opaque(value.get("diagnostic_ref"), "diagnostic", "diagnostic_ref")
def _validate_text_admission(value: object, admitted_sha: str) -> None:
    if code := text_admission_error(value, admitted_sha):
        raise WritingTypeError(code)
def _dict_list(value: object, field: str) -> list[dict]:
    if type(value) is not list or not all(type(item) is dict for item in value): raise WritingTypeError(f"{field.upper()}_INVALID")
    return list(value)
def _exact(value: dict, fields: set[str]) -> None:
    if set(value) != fields:
        raise WritingTypeError("ARTIFACT_FIELDS_INVALID")
