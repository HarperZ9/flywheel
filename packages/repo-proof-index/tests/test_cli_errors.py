from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_proof_index.cli import main
from repo_proof_index.strict_json import MAX_JSON_BYTES, MAX_JSON_DEPTH


ROOT = Path(__file__).resolve().parents[1]


def test_cli_returns_error_for_non_object_json(capsys) -> None:
    path = ROOT / "examples" / "malformed" / "not-object.json"

    assert main([str(path)]) == 1
    assert "did not contain a JSON object" in capsys.readouterr().out


def test_cli_validate_accepts_valid_proof_surface_packet(capsys) -> None:
    path = ROOT / "examples" / "contracts" / "proof-surface-packet.json"

    assert main(["--validate", str(path)]) == 0
    assert "valid" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            """
            {
              "proof_surface_version": "0.1",
              "packet_id": "dup-status",
              "surface": "evaluator-claim-handoff",
              "status": "ready",
              "status": "needs-polish",
              "claims": [{"claim": "claim", "evidence": "evidence"}],
              "checks": [{"tool": "self-report", "status": "pass", "summary": "seen"}],
              "action_items": []
            }
            """,
            "duplicate JSON key: status",
        ),
        (
            """
            {
              "proof_surface_version": "0.1",
              "packet_id": "first-id",
              "packet_id": "second-id",
              "surface": "evaluator-claim-handoff",
              "status": "ready",
              "claims": [{"claim": "claim", "evidence": "evidence"}],
              "checks": [{"tool": "self-report", "status": "pass", "summary": "seen"}],
              "action_items": []
            }
            """,
            "duplicate JSON key: packet_id",
        ),
        (
            """
            {
              "proof_surface_version": "0.1",
              "packet_id": "nan-packet",
              "surface": "evaluator-claim-handoff",
              "status": "ready",
              "claims": [{"claim": "claim", "evidence": "evidence"}],
              "checks": [{"tool": "self-report", "status": "pass", "summary": NaN}],
              "action_items": []
            }
            """,
            "non-finite JSON value: NaN",
        ),
        (
            """
            {
              "proof_surface_version": "0.1",
              "packet_id": "infinity-packet",
              "surface": "evaluator-claim-handoff",
              "status": "ready",
              "claims": [{"claim": "claim", "evidence": "evidence"}],
              "checks": [{"tool": "self-report", "status": "pass", "summary": Infinity}],
              "action_items": []
            }
            """,
            "non-finite JSON value: Infinity",
        ),
        (
            """
            {
              "proof_surface_version": "0.1",
              "packet_id": "overflow-packet",
              "surface": "evaluator-claim-handoff",
              "status": "ready",
              "claims": [{"claim": "claim", "evidence": "evidence"}],
              "checks": [{"tool": "self-report", "status": "pass", "summary": 1e999}],
              "action_items": []
            }
            """,
            "non-finite JSON value: 1e999",
        ),
    ],
)
def test_cli_validate_rejects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path, capsys, body: str, message: str
) -> None:
    path = tmp_path / "bad.packet.json"
    path.write_text(body, encoding="utf-8")

    assert main(["--validate", str(path)]) == 1

    out = capsys.readouterr().out
    assert "invalid" in out
    assert message in out


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('{"id": "first", "id": "second", "status": "pass"}', "duplicate JSON key: id"),
        ('{"id": "nan-contract", "status": NaN}', "non-finite JSON value: NaN"),
        (
            '{"id": "infinity-contract", "status": Infinity}',
            "non-finite JSON value: Infinity",
        ),
        ('{"id": "overflow-contract", "status": 1e999}', "non-finite JSON value: 1e999"),
    ],
)
def test_cli_indexing_rejects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path, capsys, body: str, message: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(body, encoding="utf-8")

    assert main([str(path)]) == 1

    out = capsys.readouterr().out
    assert out.startswith("error: ")
    assert message in out


def test_cli_validate_rejects_oversized_packet_before_validation(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "oversized.packet.json"
    path.write_text(
        (
            '{"proof_surface_version":"0.1","packet_id":"oversized",'
            '"surface":"evaluator-claim-handoff","status":"ready",'
            '"claims":[{"claim":"claim","evidence":"evidence"}],'
            '"checks":[{"tool":"self-report","status":"pass","summary":"'
            + ("x" * MAX_JSON_BYTES)
            + '"}],"action_items":[]}'
        ),
        encoding="utf-8",
    )

    assert main(["--validate", str(path)]) == 1

    out = capsys.readouterr().out
    assert "invalid" in out
    assert f"JSON file exceeds {MAX_JSON_BYTES} byte limit" in out


def test_cli_indexing_rejects_excessive_nesting(tmp_path: Path, capsys) -> None:
    path = tmp_path / "too-deep.json"
    path.write_text("[" * (MAX_JSON_DEPTH + 1) + "]" * (MAX_JSON_DEPTH + 1), encoding="utf-8")

    assert main([str(path)]) == 1

    out = capsys.readouterr().out
    assert out.startswith("error: ")
    assert f"JSON nesting exceeds {MAX_JSON_DEPTH} levels" in out


def test_cli_json_indexes_organ_exchange_artifact(tmp_path: Path, capsys) -> None:
    path = tmp_path / "organ-exchange.json"
    path.write_text(
        json.dumps(
            {
                "module_id": "orca.module.organ_exchange.bundle",
                "summary": {
                    "subject": "active-organ-pulse-smoke",
                    "bundle_status": "pass",
                    "entry_count": 3,
                    "collected_count": 3,
                    "organ_ids": ["eye.raw_rendering", "provenance.sensorium"],
                    "receipt_kinds": ["raw-health", "provenance-receipt"],
                },
                "bundle": {"bundle_id": "orb-run-active"},
            }
        ),
        encoding="utf-8",
    )

    assert main([str(path), "--json"]) == 0

    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["kind"] == "organ-exchange"
    assert rows[0]["contract"] == "orb-run-active"
    assert rows[0]["evidence"] == "entries=3, collected=3, organs=2, receipts=2"
