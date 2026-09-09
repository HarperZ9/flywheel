"""Operation-specific Writing authority predicates for projected state."""
from __future__ import annotations

from .writing_reader_flow import SOURCE_MARKER
from .writing_types import sha256_bytes


class WritingAuthorityError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def check_summary_authority(item: dict) -> None:
    if item["measurement_status"] == "checked":
        raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")
    if (item["basis"] in {"deterministic", "none"} and
            (item.get("entry_state") or item.get("new_information")
             or item.get("exit_state"))):
        raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")


def check_unit_authority(item: dict) -> None:
    if item["basis"] not in {"author_annotation", "model_annotation"} or item["measurement_status"] != "reported":
        raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")


def check_problem_authority(item: dict, body: str, sources: set[str]) -> None:
    if item["kind"] != "citation_gap":
        if item["measurement_status"] == "checked":
            raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")
        return
    source_id = item.get("source_id")
    if (item["basis"] != "deterministic" or item["measurement_status"] != "checked"
            or source_id in sources or not item["span_refs"]):
        raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")
    if any(_span_key(span) not in _marker_spans(body, source_id)
           for span in item["span_refs"]):
        raise WritingAuthorityError("SOURCE_MARKER_MISMATCH")


def check_source_marker(item: dict, body: str, sources: set[str]) -> None:
    status, source_id = item.get("status"), item.get("source_id")
    if status == "no_source_markers":
        if list(SOURCE_MARKER.finditer(body)) or item["span_refs"] or item["source_refs"]:
            raise WritingAuthorityError("SOURCE_MARKER_MISMATCH")
        if item["basis"] != "none" or item["measurement_status"] != "unsupported":
            raise WritingAuthorityError("DIAGNOSTIC_AUTHORITY_UNSUPPORTED")
        return
    if (status not in {"known_source", "unknown_source"} or not source_id
            or item["basis"] != "deterministic"
            or item["measurement_status"] != "checked" or not item["span_refs"]):
        raise WritingAuthorityError("SOURCE_MARKER_MISMATCH")
    known = source_id in sources
    if (status == "known_source") != known:
        raise WritingAuthorityError("SOURCE_REF_INVALID")
    if item["source_refs"] != ([source_id] if known else []):
        raise WritingAuthorityError("SOURCE_REF_INVALID")
    if any(_span_key(span) not in _marker_spans(body, source_id)
           for span in item["span_refs"]):
        raise WritingAuthorityError("SOURCE_MARKER_MISMATCH")


def check_diagnostic_marker_facts(diagnostic: dict, body: str,
                                  sources: set[str]) -> None:
    expected_grounding, expected_gaps = _canonical_marker_facts(
        body, sources, diagnostic["revision_ref"], diagnostic["body_sha256"])
    if not _same_unique_rows(diagnostic["source_grounding"], expected_grounding,
                             _grounding_key):
        raise WritingAuthorityError("SOURCE_MARKER_MISMATCH")
    gaps = [item for item in diagnostic["problems"]
            if item["kind"] == "citation_gap"]
    if not _same_unique_rows(gaps, expected_gaps, _problem_key):
        raise WritingAuthorityError("CITATION_GAP_MISMATCH")


def check_review_unmeasured(review: dict, decisions: list[str]) -> None:
    if review["source_coverage"]["diagnostic_ref"] != "diag_unmeasured":
        raise WritingAuthorityError("REVIEW_SOURCE_MISMATCH")
    for name in ("source_coverage", "style_lint", "quality_measurement"):
        row = review[name]
        if row["status"] != "unmeasured" or row["measurement_status"] != "unmeasured" or row["basis"] != "none" or row["source_refs"]:
            raise WritingAuthorityError("REVIEW_RESULT_UNSUPPORTED")
    row = review["scope_preservation"]
    if row["status"] != "unmeasured" or row["measurement_status"] != "unmeasured" or row["basis"] != "none":
        raise WritingAuthorityError("REVIEW_RESULT_UNSUPPORTED")
    if row["decision_refs"] != decisions:
        raise WritingAuthorityError("REVIEW_SCOPE_MISMATCH")


def check_review_measured(review: dict, diagnostic: dict) -> None:
    source = review["source_coverage"]; scope = review["scope_preservation"]
    if source["status"] != "checked" or source["basis"] != "deterministic" or source["measurement_status"] != "checked":
        raise WritingAuthorityError("REVIEW_RESULT_UNSUPPORTED")
    if source["source_refs"] != review_source_refs_from_diagnostic(diagnostic):
        raise WritingAuthorityError("REVIEW_SOURCE_COVERAGE_MISMATCH")
    if scope["status"] != "checked" or scope["basis"] != "deterministic" or scope["measurement_status"] != "checked":
        raise WritingAuthorityError("REVIEW_RESULT_UNSUPPORTED")
    for name in ("style_lint", "quality_measurement"):
        row = review[name]
        if row["status"] != "unmeasured" or row["measurement_status"] != "unmeasured" or row["basis"] != "none" or row["source_refs"]:
            raise WritingAuthorityError("REVIEW_RESULT_UNSUPPORTED")


def review_source_refs_from_diagnostic(diagnostic: dict) -> list[str]:
    refs = []
    for item in diagnostic.get("source_grounding", []):
        source_id = item.get("source_id")
        if item.get("status") == "known_source" and source_id not in refs:
            refs.append(source_id)
    return refs


def _marker_spans(body: str, source_id: str) -> set[tuple[int, int, str]]:
    return {(m.start(), m.end(), m.group(0)) for m in SOURCE_MARKER.finditer(body)
            if m.group(1) == source_id}


def _span_key(span: dict) -> tuple[int, int, str]:
    return span["start"], span["end"], span["excerpt"]


def _canonical_marker_facts(body: str, sources: set[str], revision_ref: str,
                            body_sha256: str) -> tuple[list[dict], list[dict]]:
    grounding, gaps = [], []
    for match in SOURCE_MARKER.finditer(body):
        source_id = match.group(1); known = source_id in sources
        span = {"start": match.start(), "end": match.end(),
            "excerpt": match.group(0),
            "span_sha256": sha256_bytes(match.group(0).encode("utf-8"))}
        grounding.append({"kind": "source_marker", "status":
            "known_source" if known else "unknown_source",
            "source_id": source_id, "basis": "deterministic",
            "measurement_status": "checked", "base_revision_ref": revision_ref,
            "base_body_sha256": body_sha256, "span_refs": [span],
            "source_refs": [source_id] if known else []})
        if not known:
            gaps.append({"kind": "citation_gap", "source_id": source_id,
                "basis": "deterministic", "measurement_status": "checked",
                "base_revision_ref": revision_ref,
                "base_body_sha256": body_sha256, "span_refs": [span],
                "source_refs": []})
    if not grounding:
        grounding.append({"kind": "source_marker", "status": "no_source_markers",
            "basis": "none", "measurement_status": "unsupported",
            "base_revision_ref": revision_ref, "base_body_sha256": body_sha256,
            "span_refs": [], "source_refs": []})
    return grounding, gaps


def _same_unique_rows(actual: list[dict], expected: list[dict], keyer) -> bool:
    actual_keys = [keyer(item) for item in actual]
    expected_keys = [keyer(item) for item in expected]
    return (len(actual_keys) == len(set(actual_keys))
            and sorted(actual_keys) == sorted(expected_keys))


def _grounding_key(item: dict) -> tuple:
    return (item.get("kind"), item.get("status"), item.get("source_id"),
        item.get("basis"), item.get("measurement_status"),
        item.get("base_revision_ref"), item.get("base_body_sha256"),
        tuple(_span_digest_key(span) for span in item["span_refs"]),
        tuple(item["source_refs"]))


def _problem_key(item: dict) -> tuple:
    return (item.get("kind"), item.get("source_id"), item.get("basis"),
        item.get("measurement_status"), item.get("base_revision_ref"),
        item.get("base_body_sha256"),
        tuple(_span_digest_key(span) for span in item["span_refs"]),
        tuple(item["source_refs"]))


def _span_digest_key(span: dict) -> tuple[int, int, str, str]:
    return span["start"], span["end"], span["excerpt"], span["span_sha256"]
