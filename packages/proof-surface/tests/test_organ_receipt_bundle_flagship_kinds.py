"""Cross-tool conformance: flagship receipt kinds ride the organ bundle spine.

A mixed bundle carrying one entry of every flagship kind (crucible, forum,
index, gather, learn) plus one pre-existing kind must validate with the
stdlib-only validator alone. The set stays closed: an entry claiming a kind
outside RECEIPT_KINDS must still be rejected -- extended, not opened.
"""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface import validate_organ_receipt_bundle
from proof_surface.organ_receipt_bundle import RECEIPT_KINDS

SCHEMA = (
    Path(__file__).resolve().parents[1] / "schemas" / "organ-receipt-bundle.schema.json"
)

FLAGSHIP_KINDS = {
    "crucible-assessment",
    "forum-route",
    "gather-corpus",
    "index-context-envelope",
    "learn-lesson",
    "learn-receipt",
}
EXPECTED_KINDS = FLAGSHIP_KINDS | {
    "coherence-observation",
    "emet-witness",
    "proof-surface-gate",
    "provenance-receipt",
    "raw-health",
    "tadr-classification",
    "tadr-control",
}


def _entry(entry_id: str, organ_id: str, receipt_kind: str) -> dict:
    return {
        "entry_id": entry_id,
        "organ_id": organ_id,
        "receipt_kind": receipt_kind,
        "status": "pass",
        "payload_sha256": "a" * 64,
        "summary": f"{organ_id} pass",
        "payload_ref": f"receipts/{entry_id}.json",
    }


def _mixed_bundle() -> dict:
    return {
        "organ_bundle_version": "0.1",
        "bundle_id": "orb-flagship-mixed",
        "generated_at": "2026-07-01T00:00:00Z",
        "subject": "flagship-interchange",
        "entries": [
            _entry("crucible", "judge.crucible", "crucible-assessment"),
            _entry("forum", "orchestrator.forum", "forum-route"),
            _entry("index", "map.index", "index-context-envelope"),
            _entry("gather", "intake.gather", "gather-corpus"),
            _entry("learn", "tutor.learn", "learn-receipt"),
            _entry("lesson", "loop.flywheel", "learn-lesson"),
            _entry("emet", "witness.emet", "emet-witness"),
        ],
        "edges": [
            {"from": "gather", "to": "index", "relation": "derived-from"},
            {"from": "index", "to": "forum", "relation": "observed-after"},
            {"from": "emet", "to": "crucible", "relation": "corroborates"},
        ],
        "notes": "Synthetic fixture: digests are placeholders, not real payloads.",
    }


def test_kind_vocabulary_is_exactly_the_extended_closed_set() -> None:
    assert RECEIPT_KINDS == EXPECTED_KINDS


def test_mixed_flagship_bundle_validates_zero_dep() -> None:
    assert validate_organ_receipt_bundle(_mixed_bundle()) == []


def test_unknown_receipt_kind_is_still_rejected() -> None:
    bundle = _mixed_bundle()
    bundle["entries"][0]["receipt_kind"] = "self-declared-certified"

    issues = validate_organ_receipt_bundle(bundle)

    assert any(issue.path == "$.entries[0].receipt_kind" for issue in issues)


def test_each_flagship_kind_alone_would_fail_if_dropped_from_the_set() -> None:
    # Negative fixture per kind: mutate to a near-miss spelling and require
    # rejection, so acceptance keys off set membership, not string prefixes.
    for index, kind in enumerate(sorted(FLAGSHIP_KINDS)):
        bundle = _mixed_bundle()
        bundle["entries"][index]["receipt_kind"] = kind + "-v2"
        issues = validate_organ_receipt_bundle(bundle)
        assert any(
            issue.path == f"$.entries[{index}].receipt_kind" for issue in issues
        ), kind


def test_schema_enum_stays_in_lockstep_with_validator() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    enum = schema["$defs"]["entry"]["properties"]["receipt_kind"]["enum"]
    assert set(enum) == RECEIPT_KINDS
    assert enum == sorted(enum)
