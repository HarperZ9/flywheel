"""Deterministic reader-flow and scope checks for Writing Workspace."""
from __future__ import annotations

import re

from .writing_types import WRITING_DOES_NOT_PROVE, sha256_bytes, validate_target

SOURCE_MARKER = re.compile(r"\[([A-Za-z][A-Za-z0-9_.-]{1,79})\]")


def build_diagnostic(*, project_ref: str, section_ref: str, revision_ref: str,
                     body_sha256: str, body: str,
                     source_ids: list[str] | tuple[str, ...] = ()) -> dict:
    grounding = _source_grounding(body, set(source_ids), revision_ref, body_sha256)
    problems = [{**_authority("citation_gap", "checked", revision_ref,
        body_sha256, item["span_refs"]), "message":
        "source marker has no packet entry", "source_id": item["source_id"]}
        for item in grounding if item.get("status") == "unknown_source"]
    basis = f"{revision_ref}:{body_sha256}:deterministic-v2"
    return {
        "schema": "flywheel.writing-reader-flow-diagnostic/v1",
        "project_ref": project_ref,
        "diagnostic_ref": f"diag_{sha256_bytes(basis.encode())[:32]}",
        "revision_ref": revision_ref,
        "body_sha256": body_sha256,
        "reader_state_summary": {**_authority(
            "reader_state_summary", "unmeasured", revision_ref, body_sha256,
            basis="none"),
            "entry_state": "", "new_information": [], "exit_state": ""},
        "units": [], "problems": problems, "revision_cards": [],
        "source_grounding": grounding,
        "does_not_prove": [WRITING_DOES_NOT_PROVE],
    }


def _source_grounding(body: str, source_ids: set[str], revision_ref: str,
                      body_sha256: str) -> list[dict]:
    seen = []
    for match in SOURCE_MARKER.finditer(body):
        source_id = match.group(1)
        known = source_id in source_ids
        span = {"start": match.start(), "end": match.end(),
            "excerpt": match.group(0),
            "span_sha256": sha256_bytes(match.group(0).encode("utf-8"))}
        seen.append({**_authority("source_marker", "checked", revision_ref,
            body_sha256, [span], [source_id] if known else []),
            "source_id": source_id,
            "status": "known_source" if known else "unknown_source",
            "message": "source marker checked against packet"})
    return seen or [{**_authority("source_marker", "unsupported",
        revision_ref, body_sha256, basis="none"), "status": "no_source_markers",
        "message": "no bracketed source markers were present"}]


def _authority(kind: str, status: str, revision_ref: str, body_sha256: str,
                spans: list[dict] | None = None,
               sources: list[str] | None = None,
               basis: str = "deterministic") -> dict:
    return {"kind": kind, "basis": basis,
        "measurement_status": status, "base_revision_ref": revision_ref,
        "base_body_sha256": body_sha256, "span_refs": spans or [],
        "source_refs": sources or []}


def scope_replacement_plan(base_text: str, candidate_text: str, target: dict) -> dict:
    reasons = []
    try:
        checked = validate_target(target, body=base_text)
    except Exception:
        checked = dict(target) if type(target) is dict else {}
        reasons.append("target_type")
    start, end = checked.get("start"), checked.get("end")
    if type(start) is not int or type(end) is not int:
        reasons.append("target_type")
        start, end = 0, 0
    prefix, suffix = base_text[:start], base_text[end:]
    if len(candidate_text) < len(prefix) + len(suffix):
        reasons.append("candidate_length")
    if not candidate_text.startswith(prefix):
        reasons.append("prefix")
    if not candidate_text.endswith(suffix):
        reasons.append("suffix")
    if sha256_bytes(base_text.encode("utf-8")) != checked.get("base_body_sha256"):
        reasons.append("base_body_sha256")
    selected = base_text[start:end]
    if sha256_bytes(selected.encode("utf-8")) != checked.get("selected_span_sha256"):
        reasons.append("selected_span_sha256")
    replacement = ""
    if not reasons:
        replacement = candidate_text[len(prefix):len(candidate_text) - len(suffix)]
    return {
        "verdict": "PASS" if not reasons else "HOLD",
        "failure_reasons": sorted(set(reasons)),
        "target": checked,
        "replacement_text": replacement,
        "does_not_prove": WRITING_DOES_NOT_PROVE,
    }
