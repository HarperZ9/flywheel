from __future__ import annotations

import json
from pathlib import Path

import pytest
from proof_surface.packet import validate_packet_file
from repo_proof_index.indexer import format_table, load_rows, summarize_contract, summarize_rows
from repo_proof_index.strict_json import MAX_JSON_DEPTH


FIXTURES = Path(__file__).parent / "fixtures"


def test_summarize_product_contract() -> None:
    row = summarize_contract(FIXTURES / "product.json", FIXTURES)

    assert row.contract == "product-demo"
    assert row.kind == "product-use-case"
    assert row.evidence == "pass: unit tests"


def test_load_rows_handles_multiple_shapes() -> None:
    rows = load_rows(contracts_dir=FIXTURES)

    assert {row.kind for row in rows} == {
        "backend-capability",
        "product-use-case",
        "witness-receipt",
    }
    assert "backend-matrix" in {row.status for row in rows}


def test_unknown_contract_shape_gets_best_effort_row(tmp_path: Path) -> None:
    path = tmp_path / "custom.json"
    path.write_text(json.dumps({"id": "custom", "status": "draft"}), encoding="utf-8")

    row = summarize_contract(path, tmp_path)

    assert row.contract == "custom"
    assert row.kind == "contract"
    assert row.status == "draft"


def test_summarize_orca_organ_exchange_artifact(tmp_path: Path) -> None:
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
                    "organ_ids": [
                        "eye.raw_rendering",
                        "provenance.sensorium",
                        "witness.emet",
                    ],
                    "receipt_kinds": [
                        "emet-witness",
                        "provenance-receipt",
                        "raw-health",
                    ],
                },
                "bundle": {"bundle_id": "orb-run-active"},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    row = summarize_contract(path, tmp_path)

    assert row.contract == "orb-run-active"
    assert row.kind == "organ-exchange"
    assert row.surface == "active-organ-pulse-smoke"
    assert row.status == "pass"
    assert row.evidence == "entries=3, collected=3, organs=3, receipts=3"


def test_summarize_organ_receipt_bundle(tmp_path: Path) -> None:
    path = tmp_path / "organ-receipt-bundle.json"
    path.write_text(
        json.dumps(
            {
                "organ_bundle_version": "0.1",
                "bundle_id": "orb-demo",
                "subject": "workspace-organ-health",
                "entries": [
                    {
                        "entry_id": "raw-health",
                        "organ_id": "eye.raw_rendering",
                        "receipt_kind": "raw-health",
                        "status": "pass",
                    },
                    {
                        "entry_id": "emet-witness",
                        "organ_id": "witness.emet",
                        "receipt_kind": "emet-witness",
                        "status": "warn",
                    },
                ],
                "edges": [{"from": "raw-health", "to": "emet-witness"}],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    row = summarize_contract(path, tmp_path)

    assert row.contract == "orb-demo"
    assert row.kind == "organ-receipt-bundle"
    assert row.surface == "workspace-organ-health"
    assert row.status == "warn"
    assert row.evidence == "entries=2, edges=1, organs=2, receipts=2"


def test_format_table_includes_contract_evidence() -> None:
    table = format_table(load_rows([FIXTURES / "product.json"], root=FIXTURES))

    assert "product-use-case" in table
    assert "unit tests" in table


def test_valid_proof_surface_packet_fixture_passes_validation() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "conformance"
        / "proof-surface"
        / "v0.1"
        / "valid"
        / "minimal.packet.json"
    )

    assert validate_packet_file(path) == []


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
        ('{"id": "nan-contract", "status": NaN}', "non-finite JSON value: NaN"),
        ('{"id": "inf-contract", "status": Infinity}', "non-finite JSON value: Infinity"),
        ('{"id": "overflow-contract", "status": 1e999}', "non-finite JSON value: 1e999"),
        (
            '{"id": "negative-overflow-contract", "status": -1e999}',
            "non-finite JSON value: -1e999",
        ),
    ],
)
def test_api_rejects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path, body: str, message: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        summarize_contract(path, tmp_path)


def test_api_rejects_excessively_nested_json(tmp_path: Path) -> None:
    path = tmp_path / "too-deep.json"
    path.write_text("[" * (MAX_JSON_DEPTH + 1) + "]" * (MAX_JSON_DEPTH + 1), encoding="utf-8")

    with pytest.raises(ValueError, match=f"JSON nesting exceeds {MAX_JSON_DEPTH} levels"):
        summarize_contract(path, tmp_path)


def test_proof_surface_ready_packet_is_marked_producer_declared_not_verified(
    tmp_path: Path,
) -> None:
    path = tmp_path / "false-success-self-declared-match.packet.json"
    path.write_text(
        json.dumps(
            {
                "proof_surface_version": "0.1",
                "packet_id": "false-success-self-declared-match-20260913",
                "surface": "evaluator-claim-handoff",
                "status": "ready",
                "claims": [
                    {
                        "claim": "Synthetic evaluator record fail-001 is MATCH.",
                        "evidence": (
                            "producer self-declared MATCH only; intentionally omits "
                            "Crucible measurement that shows absolute_score_error=1.0 > 0.5"
                        ),
                    }
                ],
                "checks": [
                    {
                        "tool": "producer-self-report",
                        "status": "pass",
                        "summary": "Self-reported green check; no verifier command embedded.",
                    }
                ],
                "action_items": [],
            }
        ),
        encoding="utf-8",
    )

    row = summarize_contract(path, tmp_path)
    summary = summarize_rows([row])

    assert row.status == "ready"
    assert row.producer_status == "ready"
    assert row.verification_state == "not_verified"
    assert row.evidence == (
        "declared=ready, verification=not_verified, claims=1, checks=1, actions=0"
    )
    assert summary.action_items == [
        "false-success-self-declared-match-20260913: verify producer-declared ready "
        "(false-success-self-declared-match.packet.json)"
    ]


def test_research_claim_packet_indexes_reported_verdict_without_verifying(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research-claim-packet.json"
    path.write_text(
        json.dumps(
            {
                "version": "research-claim-proof-packet/v0",
                "packet_id": "synthetic-evaluator-claims-20260913",
                "claim": (
                    "Synthetic evaluator-claim packet preserves one correct claim, "
                    "one wrong self-declared claim, and one missing-evidence claim."
                ),
                "scope": "Disposable public-clean handoff experiment.",
                "sources": [
                    {
                        "availability": "open",
                        "ref": "crucible/bundle/run.json",
                        "sha256": "0" * 64,
                    }
                ],
                "attempts": [
                    {
                        "attempt_id": "crucible-offline-recheck-20260913",
                        "method": "python -m crucible run/review/verdicts",
                        "result": "bounded",
                        "artifact_ref": "crucible/bundle/run.json",
                    }
                ],
                "checks": [
                    {"checker": "correct", "status": "pass", "evidence": ["MATCH"]},
                    {"checker": "wrong", "status": "fail", "evidence": ["DRIFT"]},
                    {
                        "checker": "missing",
                        "status": "unverifiable",
                        "evidence": ["UNVERIFIABLE"],
                    },
                ],
                "verdicts": {
                    "overall": "UNVERIFIABLE",
                    "per_check": [
                        {"checker": "correct", "status": "MATCH"},
                        {"checker": "wrong", "status": "DRIFT"},
                        {"checker": "missing", "status": "UNVERIFIABLE"},
                    ],
                },
                "promotion": "UNVERIFIABLE",
                "uncertainty": ["missing evidence remains"],
            }
        ),
        encoding="utf-8",
    )

    row = summarize_contract(path, tmp_path)

    assert row.contract == "synthetic-evaluator-claims-20260913"
    assert row.kind == "research-claim-packet"
    assert row.status == "UNVERIFIABLE"
    assert row.producer_status == "UNVERIFIABLE"
    assert row.verification_state == "not_verified"
    assert row.evidence == (
        "reported=UNVERIFIABLE, verification=not_verified, "
        "promotion=UNVERIFIABLE, checks: DRIFT=1, MATCH=1, UNVERIFIABLE=1"
    )


def test_empty_claims_and_checks_are_invalid(tmp_path: Path) -> None:
    path = tmp_path / "empty.packet.json"
    path.write_text(
        json.dumps(
            {
                "proof_surface_version": "0.1",
                "packet_id": "empty",
                "surface": "empty proof surface",
                "status": "unknown",
                "claims": [],
                "checks": [],
                "action_items": [],
            }
        ),
        encoding="utf-8",
    )

    messages = {(issue.path, issue.message) for issue in validate_packet_file(path)}

    assert ("$.claims", "expected at least 1 item(s)") in messages
    assert ("$.checks", "expected at least 1 item(s)") in messages
