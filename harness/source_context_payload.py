"""Validation and projections for source-context private payloads."""
from __future__ import annotations

import hashlib
import re

from .evidence_json import canonical_sha256
from .evidence_public import public_metadata
from .source_context_error import SourceContextError

PRIVATE_SCHEMA = "flywheel.source-context-private/v1"
PROJECTION_SCHEMA = "flywheel.source-context-projection/v1"
BINDING_SCHEMA = "flywheel.source-context-binding/v1"
WORKER_SCHEMA = "flywheel.source-context-worker-payload/v1"
SOURCE_REF_PREFIX = "data_source_context."
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_ROW_REF = re.compile(r"row_[0-9a-f]{32}\Z|row_[A-Za-z0-9._-]{1,64}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_CAP_FIELDS = ("max_rows", "max_total_chars", "default_limit",
    "max_catalog_bytes", "max_catalog_rows", "max_body_bytes", "max_read_bytes")
_CAP_LIMITS = {"max_rows": 50, "max_total_chars": 100_000,
    "default_limit": 100_000, "max_catalog_bytes": 100_000_000,
    "max_catalog_rows": 100_000, "max_body_bytes": 100_000_000,
    "max_read_bytes": 100_000_000}


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _safe_name(value: object, code: str = "INVALID_REQUEST") -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise SourceContextError(code)
    return value


def _hex(value: object, code: str = "SOURCE_CONTEXT_SELECTION_FAILED") -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise SourceContextError(code)
    return value


def validated_gather_payload(payload: dict) -> tuple[list[dict], dict]:
    if (type(payload) is not dict or payload.get("schema") != "gather.readable-context/v1"
            or payload.get("verified") is not True
            or payload.get("verified_scope") != "selected_rows"):
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    _public_list(payload.get("omissions") or [])
    _public_list(payload.get("does_not_prove") or [])
    base = {key: value for key, value in payload.items()
            if key not in {"selection_digest", "verified", "verified_scope"}}
    try:
        digest = canonical_sha256(base)
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED") from None
    if _hex(payload.get("selection_digest")) != digest:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    caps, rows = _caps(payload), _rows(payload)
    total = payload.get("total_text_chars")
    if (payload.get("selection_count") != len(rows) or type(total) is not int
            or total != sum(len(row["text"]) for row in rows)
            or len(rows) > caps.get("max_rows", _CAP_LIMITS["max_rows"])
            or total > caps.get("max_total_chars", _CAP_LIMITS["max_total_chars"])):
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    if any(row["body_bytes_read"] > caps.get("max_body_bytes", _CAP_LIMITS["max_body_bytes"])
           for row in rows):
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    return rows, caps


def _rows(payload: dict) -> list[dict]:
    rows = payload.get("selections")
    if type(rows) is not list or not rows:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    return [_row(row) for row in rows]


def _row(row: dict) -> dict:
    span, text = row.get("range"), row.get("text")
    if type(row) is not dict or type(span) is not dict or type(text) is not str or "\r" in text:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    start, end = span.get("start"), span.get("end")
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    row_ref, full_hash = row.get("row_ref"), row.get("verified_sha256") or row.get("sha256")
    if type(row_ref) is not str or _ROW_REF.fullmatch(row_ref) is None:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    try:
        full_chars = int(row.get("full_text_chars", 0))
        body_bytes = int(row.get("body_bytes_read", 0))
    except (TypeError, ValueError):
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED") from None
    if full_chars < 0 or body_bytes < 0:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    return {"row_ref": row_ref, "kind": _safe_name(row.get("kind")),
        "id_sha256": _sha_text(str(row.get("id", ""))),
        "source_ref_sha256": _sha_text(str(row.get("ref", ""))),
        "method": _safe_name(row.get("method")),
        "normalized_full_text_sha256": _hex(full_hash),
        "range": {"start": start, "end": end}, "text": text,
        "selected_text_utf8_bytes": len(text.encode("utf-8", "strict")),
        "selected_text_utf8_sha256": _sha_text(text),
        "full_text_chars": full_chars, "body_bytes_read": body_bytes,
        "omissions": _public_list(row.get("omissions") or [])}


def projection_for(ref: str, private: dict, private_hash: str) -> dict:
    rows = [{"row_ref": row["row_ref"], "range": row["range"],
        "selected_text_utf8_bytes": row["selected_text_utf8_bytes"],
        "selected_text_utf8_sha256_prefix": row["selected_text_utf8_sha256"][:16],
        "normalized_full_text_sha256_prefix": row["normalized_full_text_sha256"][:16],
        "omissions": row["omissions"]} for row in private["rows"]]
    projection = {"schema": PROJECTION_SCHEMA, "source_context_ref": ref,
        "private_payload_sha256": private_hash, "root_mode": private["root_mode"],
        "profile": private["profile"], "row_count": private["row_count"],
        "rows": rows, "selected_text_utf8_bytes": private["selected_text_utf8_bytes"],
        "caps": private["caps"], "omissions": private["omissions"],
        "does_not_prove": private["does_not_prove"]}
    try:
        public_metadata(projection)
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED") from None
    return projection


def journey_basis_for(ref: str, projection: dict) -> dict:
    return {"source_context_ref": ref, "projection_sha256": canonical_sha256(projection),
        "row_count": projection["row_count"],
        "selected_text_utf8_bytes": projection["selected_text_utf8_bytes"],
        "omissions": projection["omissions"], "does_not_prove": projection["does_not_prove"]}


def worker_context_for(private: dict, projection: dict, binding: dict) -> dict:
    rows = [{"row_ref": row["row_ref"], "range": row["range"],
        "text": row["text"], "selected_text_utf8_bytes": row["selected_text_utf8_bytes"],
        "selected_text_utf8_sha256": row["selected_text_utf8_sha256"],
        "normalized_full_text_sha256": row["normalized_full_text_sha256"],
        "omissions": row["omissions"]} for row in private["rows"]]
    return {"source_context_ref": binding["source_context_ref"],
        "private_payload_sha256": binding["private_payload_sha256"],
        "projection_sha256": binding["projection_sha256"], "projection": projection,
        "rows": rows, "does_not_prove": private["does_not_prove"]}

def _caps(payload: dict) -> dict:
    caps = {}
    for key in _CAP_FIELDS:
        if key in payload:
            value = payload[key]
            if type(value) is not int or value < 1 or value > _CAP_LIMITS[key]:
                raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
            caps[key] = value
    return caps


def _public_list(value: object) -> list:
    if type(value) is not list:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    try:
        public_metadata(value)
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED") from None
    return list(value)
