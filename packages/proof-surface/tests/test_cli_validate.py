from __future__ import annotations

import json
from pathlib import Path

import pytest

from proof_surface.cli import main


ROOT = Path(__file__).resolve().parents[1]
RAW_AUTHORIZATION_INVALIDS = (
    "duplicate-revoked.receipt.json",
    "duplicate-action.receipt.json",
    "duplicate-target.receipt.json",
    "duplicate-max-actions.receipt.json",
    "duplicate-escaped-action.receipt.json",
    "nan-max-actions.receipt.json",
    "infinity-max-actions.receipt.json",
    "negative-infinity-max-actions.receipt.json",
)


def test_validate_cli_accepts_tadr_bundle(capsys) -> None:
    path = (
        ROOT
        / "conformance"
        / "organ-receipt-bundle"
        / "v0.1"
        / "valid"
        / "tadr-kinds.bundle.json"
    )

    assert main(["validate", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "MATCH"
    assert result["contract"] == "organ-receipt-bundle/v0.1"


def test_validate_cli_rejects_zero_digest(capsys) -> None:
    path = (
        ROOT
        / "conformance"
        / "organ-receipt-bundle"
        / "v0.1"
        / "invalid"
        / "tadr-zero-digest.bundle.json"
    )

    assert main(["validate", str(path)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["issues"][0]["path"] == "$.entries[0].payload_sha256"


def test_validate_cli_accepts_authorization_v0_2(capsys) -> None:
    path = (
        ROOT
        / "conformance"
        / "authorization-receipt"
        / "v0.2"
        / "valid"
        / "minimal.receipt.json"
    )

    assert main(["validate", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "MATCH"
    assert result["contract"] == "authorization-receipt/v0.2"


def test_validate_cli_fails_closed_on_unknown_contract(tmp_path, capsys) -> None:
    path = tmp_path / "unknown.json"
    path.write_text('{"schema":"unknown/v1"}', encoding="utf-8")

    assert main(["validate", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["reason"] == "unknown_contract"


@pytest.mark.parametrize("filename", RAW_AUTHORIZATION_INVALIDS)
def test_validate_cli_rejects_ambiguous_authorization_json(
    filename: str, capsys
) -> None:
    path = (
        ROOT
        / "conformance"
        / "authorization-receipt"
        / "v0.2"
        / "invalid"
        / filename
    )

    assert main(["validate", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["reason"] == "malformed_document"
    assert "strict loader" in result["issues"][0]["message"]
