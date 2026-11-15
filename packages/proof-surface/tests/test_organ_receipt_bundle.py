from __future__ import annotations

import json
from pathlib import Path

import pytest

from proof_surface import validate_organ_receipt_bundle

SCHEMA = (
    Path(__file__).resolve().parents[1] / "schemas" / "organ-receipt-bundle.schema.json"
)


def _entry(
    entry_id: str,
    organ_id: str,
    receipt_kind: str,
    status: str = "pass",
) -> dict:
    return {
        "entry_id": entry_id,
        "organ_id": organ_id,
        "receipt_kind": receipt_kind,
        "status": status,
        "payload_sha256": "a" * 64,
        "summary": f"{organ_id} {status}",
        "payload_ref": f"receipts/{entry_id}.json",
    }


def _bundle() -> dict:
    return {
        "organ_bundle_version": "0.1",
        "bundle_id": "orb-demo",
        "generated_at": "2026-06-19T09:10:00Z",
        "subject": "workspace-organ-health",
        "entries": [
            _entry("raw", "eye.raw_rendering", "raw-health"),
            _entry("emet", "witness.emet", "emet-witness"),
            _entry("sensorium", "provenance.sensorium", "provenance-receipt"),
            _entry("coherence", "membrane.coherence", "coherence-observation"),
            _entry("gate", "gate.proof_surface", "proof-surface-gate", "needs-human"),
        ],
        "edges": [
            {"from": "raw", "to": "coherence", "relation": "observed-after"},
            {"from": "emet", "to": "gate", "relation": "gates"},
            {"from": "sensorium", "to": "gate", "relation": "corroborates"},
        ],
        "notes": "Bundle holds digests and refs, not authority.",
    }


def test_valid_organ_receipt_bundle_accepts_cross_organ_entries() -> None:
    assert validate_organ_receipt_bundle(_bundle()) == []


def test_bundle_requires_entries() -> None:
    bundle = _bundle()
    bundle["entries"] = []

    issues = validate_organ_receipt_bundle(bundle)

    assert any(issue.path == "$.entries" for issue in issues)


def test_bundle_rejects_duplicate_entry_ids_and_bad_edge_refs() -> None:
    bundle = _bundle()
    bundle["entries"].append(_entry("raw", "eye.raw_rendering", "raw-health"))
    bundle["edges"].append({"from": "missing", "to": "raw", "relation": "derived-from"})

    issues = validate_organ_receipt_bundle(bundle)

    assert any("duplicate entry_id" in issue.message for issue in issues)
    assert any(issue.path == "$.edges[3].from" for issue in issues)


def test_bundle_rejects_payload_content_and_authority_fields() -> None:
    bundle = _bundle()
    bundle["entries"][0]["payload"] = {"too": "large"}
    bundle["entries"][1]["guardrail_posture"] = "trusted"

    issues = validate_organ_receipt_bundle(bundle)

    assert any(issue.path == "$.entries[0].payload" for issue in issues)
    assert any(
        "guardrail_posture" in issue.path and "forbidden" in issue.message
        for issue in issues
    )


def test_json_schema_accepts_bundle_shape() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    assert list(validator.iter_errors(_bundle())) == []
