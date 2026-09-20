"""Data-only standards profile validation for the first registry slice."""
from __future__ import annotations

from typing import Any

from .standards_schema import (
    APPLICABILITY_FIELDS, BINDING_BASES, BINDING_REVIEWS, Collector,
    DISCLOSURE_TIERS, EFFECTIVE_FIELDS, EVIDENCE_FIELDS, EVIDENCE_STATUSES,
    EXEC_KEYS, INSTRUMENT_FIELDS, INSTRUMENT_KINDS, ISSUER_ROLES,
    PROFILE_SCHEMA, PROVENANCE_FIELDS, REQUIREMENT_FIELDS, REVIEW_STATUSES,
    ROOT_FIELDS, SOURCE_STATUSES, VALIDATION_SCHEMA, is_sha256, parse_date,
)


def _reject_unknown(obj: dict[str, Any], allowed: set[str], path: str,
                    c: Collector) -> None:
    for key in obj:
        lowered = key.lower()
        if lowered in EXEC_KEYS:
            c.error(f"{path}.{key}", "executable_field",
                    "executable field is not allowed")
        elif key not in allowed:
            c.error(f"{path}.{key}", "unknown_field", "unknown field")


def _scan_executable(value: object, path: str, c: Collector) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in EXEC_KEYS:
                c.error(f"{path}.{key}", "executable_field",
                        "executable field is not allowed")
            _scan_executable(child, f"{path}.{key}", c)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _scan_executable(child, f"{path}[{i}]", c)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in ("__import__", "subprocess")):
            c.error(path, "executable_value",
                    "executable value is not allowed")


def _expect_dict(parent: dict[str, Any], key: str, path: str,
                 c: Collector) -> dict[str, Any] | None:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    c.error(f"{path}.{key}", "type", "expected object")
    return None


def _expect_string(obj: dict[str, Any], key: str, path: str,
                   c: Collector, *, nullable: bool = False) -> str | None:
    value = obj.get(key)
    if value is None and nullable:
        return None
    if isinstance(value, str) and value:
        return value
    c.error(f"{path}.{key}", "type", "expected string")
    return None


def _expect_bool(obj: dict[str, Any], key: str, path: str,
                 c: Collector) -> bool | None:
    value = obj.get(key)
    if isinstance(value, bool):
        return value
    c.error(f"{path}.{key}", "type", "expected boolean")
    return None


def _expect_enum(obj: dict[str, Any], key: str, allowed: set[str], path: str,
                 c: Collector) -> str | None:
    value = _expect_string(obj, key, path, c)
    if value is not None and value not in allowed:
        c.error(f"{path}.{key}", "enum", "unknown enum value")
    return value


def _expect_str_list(obj: dict[str, Any], key: str, path: str,
                     c: Collector, *, allow_empty: bool = False) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or (not allow_empty and not value):
        c.error(f"{path}.{key}", "type", "expected non-empty string list")
        return []
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            c.error(f"{path}.{key}[{i}]", "type", "expected string")
        else:
            out.append(item)
    return out


def _validate_required(obj: dict[str, Any], fields: set[str], path: str,
                       c: Collector) -> None:
    for field in sorted(fields):
        if field not in obj:
            c.error(f"{path}.{field}", "missing", "required field missing")


def _validate_profile(profile: dict[str, Any], c: Collector) -> None:
    _scan_executable(profile, "$", c)
    _reject_unknown(profile, ROOT_FIELDS, "$", c)
    _validate_required(profile, ROOT_FIELDS, "$", c)
    if profile.get("schema") != PROFILE_SCHEMA:
        c.error("$.schema", "schema", "expected flywheel.standards-profile/v1")
    for key in ("profile_id", "title", "version", "owner", "does_not_prove"):
        _expect_string(profile, key, "$", c)

    instrument = _expect_dict(profile, "instrument", "$", c)
    if instrument:
        _reject_unknown(instrument, INSTRUMENT_FIELDS, "$.instrument", c)
        _validate_required(instrument, INSTRUMENT_FIELDS, "$.instrument", c)
        for key in ("instrument_id", "title", "edition", "jurisdiction"):
            _expect_string(instrument, key, "$.instrument", c)
        _expect_enum(instrument, "instrument_kind", INSTRUMENT_KINDS,
                     "$.instrument", c)
        _expect_enum(instrument, "issuer_role", ISSUER_ROLES, "$.instrument", c)
        _expect_enum(instrument, "binding_basis", BINDING_BASES,
                     "$.instrument", c)
        _expect_enum(instrument, "binding_review_status", BINDING_REVIEWS,
                     "$.instrument", c)

    provenance = _expect_dict(profile, "provenance", "$", c)
    if provenance:
        _reject_unknown(provenance, PROVENANCE_FIELDS, "$.provenance", c)
        _validate_required(provenance, PROVENANCE_FIELDS, "$.provenance", c)
        status = _expect_enum(provenance, "source_status", SOURCE_STATUSES,
                              "$.provenance", c)
        review = _expect_enum(provenance, "review_status", REVIEW_STATUSES,
                              "$.provenance", c)
        for key in ("source_ref", "language", "translation"):
            _expect_string(provenance, key, "$.provenance", c)
        _expect_string(provenance, "source_url", "$.provenance", c,
                       nullable=True)
        _expect_enum(provenance, "disclosure_tier", DISCLOSURE_TIERS,
                     "$.provenance", c)
        parse_date(provenance.get("retrieved_at"), "$.provenance.retrieved_at",
                   c)
        source_hash = provenance.get("source_sha256")
        null_reason = provenance.get("raw_source_hash_null_reason")
        if source_hash is None:
            _expect_string(provenance, "raw_source_hash_null_reason",
                           "$.provenance", c)
        elif not is_sha256(source_hash):
            c.error("$.provenance.source_sha256", "hash", "expected sha256")
        if source_hash is not None and null_reason is not None:
            c.error("$.provenance.source_sha256", "contradiction",
                    "source_sha256 conflicts with raw_source_hash_null_reason")
        if (status == "full_text_reviewed" or review == "reviewed") and \
                source_hash is None:
            c.error("$.provenance.source_sha256", "contradiction",
                    "reviewed source requires source_sha256")
        if status != "full_text_reviewed" or review != "reviewed":
            c.gap("$.provenance", "source_not_full_text_reviewed",
                  "source metadata is not reviewed full text")

    effective = _expect_dict(profile, "effective", "$", c)
    if effective:
        _reject_unknown(effective, EFFECTIVE_FIELDS, "$.effective", c)
        _validate_required(effective, EFFECTIVE_FIELDS, "$.effective", c)
        start = parse_date(effective.get("effective_from"),
                           "$.effective.effective_from", c)
        end = parse_date(effective.get("effective_to"),
                         "$.effective.effective_to", c)
        parse_date(effective.get("published_on"), "$.effective.published_on", c)
        _expect_str_list(effective, "supersedes", "$.effective", c,
                         allow_empty=True)
        _expect_str_list(effective, "superseded_by", "$.effective", c,
                         allow_empty=True)
        if start and end and end < start:
            c.error("$.effective.effective_to", "date_range",
                    "effective_to precedes effective_from")

    applicability = _expect_dict(profile, "applicability", "$", c)
    if applicability:
        _validate_selectors(applicability, "$.applicability", c)

    _validate_requirements(profile.get("requirements"), c)


def _validate_selectors(value: object, path: str, c: Collector) -> None:
    if not isinstance(value, dict):
        c.error(path, "type", "expected object")
        return
    _reject_unknown(value, APPLICABILITY_FIELDS, path, c)
    _validate_required(value, APPLICABILITY_FIELDS, path, c)
    for key in sorted(APPLICABILITY_FIELDS):
        _expect_str_list(value, key, path, c)


def _validate_requirements(value: object, c: Collector) -> None:
    if not isinstance(value, list) or not value:
        c.error("$.requirements", "type", "expected non-empty requirement list")
        return
    seen: set[str] = set()
    for i, req in enumerate(value):
        path = f"$.requirements[{i}]"
        if not isinstance(req, dict):
            c.error(path, "type", "expected object")
            continue
        _reject_unknown(req, REQUIREMENT_FIELDS, path, c)
        _validate_required(req, REQUIREMENT_FIELDS, path, c)
        req_id = _expect_string(req, "requirement_id", path, c)
        if req_id:
            if req_id in seen:
                c.error(f"{path}.requirement_id", "duplicate",
                        "duplicate requirement_id")
            seen.add(req_id)
        for key in ("requirement_ref", "summary", "does_not_prove"):
            _expect_string(req, key, path, c)
        if not is_sha256(req.get("text_hash")):
            c.error(f"{path}.text_hash", "hash", "expected sha256")
        _validate_selectors(req.get("selectors"), f"{path}.selectors", c)
        _expect_str_list(req, "maps_to_controls", path, c, allow_empty=True)
        _expect_str_list(req, "maps_to_evidence_claims", path, c,
                         allow_empty=True)
        _expect_bool(req, "review_required", path, c)
        evidence = _expect_dict(req, "evidence", path, c)
        if evidence:
            _reject_unknown(evidence, EVIDENCE_FIELDS, f"{path}.evidence", c)
            _validate_required(evidence, EVIDENCE_FIELDS,
                               f"{path}.evidence", c)
            _expect_enum(evidence, "status", EVIDENCE_STATUSES,
                         f"{path}.evidence", c)
            status = evidence.get("status")
            artifact = evidence.get("artifact_sha256")
            if status in ("observed", "independently_reproduced") and \
                    artifact is None:
                c.error(f"{path}.evidence.artifact_sha256", "missing",
                        "observed evidence requires artifact_sha256")
            if artifact is not None and not is_sha256(artifact):
                c.error(f"{path}.evidence.artifact_sha256", "hash",
                        "expected sha256")


def validate_profile_object(profile: object) -> dict[str, Any]:
    c = Collector()
    if not isinstance(profile, dict):
        c.error("$", "type", "profile must be an object")
        profile_summary = None
    else:
        _validate_profile(profile, c)
        profile_summary = None if c.errors else {
            "profile_id": profile["profile_id"],
            "version": profile["version"],
            "requirements": len(profile["requirements"]),
        }
    return {
        "schema": VALIDATION_SCHEMA,
        "verdict": "INVALID" if c.errors else "VALID",
        "profile": profile_summary,
        "assessment": "not_assessed",
        "errors": c.errors,
        "gaps": c.gaps,
        "does_not_prove": (
            "Profile validation checks data shape only; it does not prove "
            "legal compliance, source truth, certification, or approval."),
    }
