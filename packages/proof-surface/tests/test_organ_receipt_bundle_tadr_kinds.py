"""Conformance checks for TADR entries on the organ receipt bundle spine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proof_surface import validate_organ_receipt_bundle

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "conformance" / "organ-receipt-bundle" / "v0.1"
SCHEMA = ROOT / "schemas" / "organ-receipt-bundle.schema.json"


def _load(relative_path: str) -> dict:
    return json.loads((CONF / relative_path).read_text(encoding="utf-8"))


def test_mixed_tadr_bundle_validates() -> None:
    assert validate_organ_receipt_bundle(_load("valid/tadr-kinds.bundle.json")) == []


def test_zero_control_digest_is_rejected() -> None:
    issues = validate_organ_receipt_bundle(
        _load("invalid/tadr-zero-digest.bundle.json")
    )

    assert any(
        issue.path == "$.entries[0].payload_sha256" and "nonzero" in issue.message
        for issue in issues
    )


def test_tadr_conformance_manifest_matches_validator() -> None:
    manifest = _load("manifest.json")

    for fixture in manifest["fixtures"]:
        issues = validate_organ_receipt_bundle(_load(fixture["path"]))
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid"


def test_tadr_vectors_match_published_json_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    )

    assert list(validator.iter_errors(_load("valid/tadr-kinds.bundle.json"))) == []
    assert list(validator.iter_errors(_load("invalid/tadr-zero-digest.bundle.json")))
