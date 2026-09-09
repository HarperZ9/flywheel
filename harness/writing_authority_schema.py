"""Shared Writing V2 authority and text-admission schema checks."""
from __future__ import annotations

import hashlib
import re

AUTHORITY_FIELDS = {"kind", "basis", "measurement_status", "base_revision_ref",
    "base_body_sha256", "span_refs", "source_refs"}
ANALYZER_FIELDS = {"analyzer_ref", "analyzer_sha256"}
BASIS_VALUES = {"deterministic", "author_annotation", "model_annotation", "none"}
MEASUREMENT_VALUES = {"checked", "reported", "unmeasured", "unsupported"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def admit_text(raw: str | bytes, *, max_bytes: int) -> tuple[str, bytes, dict]:
    if isinstance(raw, str):
        data = raw.encode("utf-8", "strict")
    elif isinstance(raw, bytes):
        data = raw
    else:
        raise ValueError("TEXT_INVALID")
    if len(data) > max_bytes:
        raise ValueError("TEXT_TOO_LARGE")
    try:
        original = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError("TEXT_INVALID") from exc
    text = original.replace("\r\n", "\n").replace("\r", "\n")
    normalized = text.encode("utf-8", "strict")
    if len(normalized) > max_bytes:
        raise ValueError("TEXT_TOO_LARGE")
    receipt = {"coordinate_type": "unicode_codepoint",
        "coordinate_basis": "admitted_lf_text",
        "input_newline": _newline_kind(original), "stored_newline": "lf",
        "converted_crlf": "\r\n" in original,
        "converted_cr": "\r" in original.replace("\r\n", ""),
        "input_sha256": sha256_bytes(data),
        "admitted_sha256": sha256_bytes(normalized)}
    return text, normalized, receipt


def authority_shape_error(item: object, extra: set[str], field: str) -> str | None:
    if type(item) is not dict:
        return f"{field.upper()}_INVALID"
    if not AUTHORITY_FIELDS.issubset(item) or set(item) - AUTHORITY_FIELDS - extra - ANALYZER_FIELDS:
        return f"{field.upper()}_INVALID"
    return None


def authority_tuple_error(item: dict, field: str) -> str | None:
    basis, status = item.get("basis"), item.get("measurement_status")
    if basis not in BASIS_VALUES or status not in MEASUREMENT_VALUES:
        return f"{field.upper()}_AUTHORITY_INVALID"
    if basis in {"author_annotation", "model_annotation"} and status != "reported":
        return f"{field.upper()}_AUTHORITY_INVALID"
    if basis == "none" and status not in {"unmeasured", "unsupported"}:
        return f"{field.upper()}_AUTHORITY_INVALID"
    if basis == "deterministic" and status == "reported":
        return f"{field.upper()}_AUTHORITY_INVALID"
    return _analyzer_error(item)


def review_result_shape_error(value: object, extra: set[str], field: str) -> str | None:
    if type(value) is not dict:
        return f"{field.upper()}_INVALID"
    allowed = {"status", "basis", "measurement_status"} | extra | ANALYZER_FIELDS
    if set(value) - allowed or not {"status", "basis", "measurement_status"}.issubset(value):
        return f"{field.upper()}_INVALID"
    basis, measured, status = value["basis"], value["measurement_status"], value["status"]
    if basis not in BASIS_VALUES or measured not in MEASUREMENT_VALUES or type(status) is not str:
        return f"{field.upper()}_INVALID"
    if ((measured == "unmeasured" and status != "unmeasured")
            or (measured == "checked" and status in {"unmeasured", "unsupported"})
            or (measured == "reported" and basis not in {"author_annotation", "model_annotation"})
            or (measured == "unsupported" and status not in {"unsupported", "unmeasured"})):
        return f"{field.upper()}_INVALID"
    return _analyzer_error(value)


def text_admission_error(value: object, admitted_sha: str) -> str | None:
    fields = {"coordinate_type", "coordinate_basis", "input_newline",
        "stored_newline", "converted_crlf", "converted_cr", "input_sha256",
        "admitted_sha256"}
    if type(value) is not dict or set(value) != fields:
        return "TEXT_ADMISSION_INVALID"
    if (value.get("coordinate_type") != "unicode_codepoint"
            or value.get("coordinate_basis") != "admitted_lf_text"
            or value.get("stored_newline") != "lf"
            or value.get("input_newline") not in {"none", "lf", "crlf", "cr", "mixed"}
            or type(value.get("converted_crlf")) is not bool
            or type(value.get("converted_cr")) is not bool):
        return "TEXT_ADMISSION_INVALID"
    if (not _sha(value.get("input_sha256")) or not _sha(value.get("admitted_sha256"))
            or value["admitted_sha256"] != admitted_sha):
        return "TEXT_ADMISSION_INVALID"
    return None


def _analyzer_error(item: dict) -> str | None:
    if item.get("basis") == "model_annotation":
        if not (_safe(item.get("analyzer_ref")) and _sha(item.get("analyzer_sha256"))):
            return "ANALYZER_PROVENANCE_INVALID"
    elif any(key in item for key in ANALYZER_FIELDS):
        return "ANALYZER_PROVENANCE_INVALID"
    return None


def _newline_kind(text: str) -> str:
    crlf = "\r\n" in text
    lone = "\r" in text.replace("\r\n", "")
    lf = "\n" in text.replace("\r\n", "")
    if sum(1 for item in (crlf, lone, lf) if item) > 1:
        return "mixed"
    return "crlf" if crlf else "cr" if lone else "lf" if lf else "none"


def _safe(value: object) -> bool:
    return type(value) is str and SAFE_ID_PATTERN.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return type(value) is str and SHA256_PATTERN.fullmatch(value) is not None
