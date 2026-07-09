import json

from harness.model_card_claims import build_claim_table, render_markdown


def contract_fixture():
    return {
        "schema": "harness.benchmark-contract/v1",
        "source_feedback": {
            "source_label": "operator-relayed community feedback",
            "model_leads_unverified": ["Qwythos-9B-Claude-Mythos-5-1M", "Gemma 4 multimodal"],
        },
        "verified_facts": ["The feedback asks about realtime senses."],
        "assumptions_to_verify_before_result_claims": ["Whether each named model exists."],
    }


def test_claim_table_marks_relayed_model_leads_unverified_without_evidence():
    table = build_claim_table(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        artifact_dir="C:/tmp/model-card-claims",
        run_id="run_123",
    )

    assert table["schema"] == "harness.model-card-claim-table/v1"
    assert table["summary"]["model_candidates"] == 2
    assert table["summary"]["provider_execution"] is False
    assert table["summary"]["endpoint_probe"] is False
    assert table["summary"]["model_weight_read"] is False
    assert table["summary"]["network_fetch"] is False
    assert table["summary"]["not_checked_fields"] == 16
    assert table["summary"]["unresolved_fields"] == 16
    assert table["model_rows"][0]["overall_claim_status"] == "operator_relayed_unverified"
    json.dumps(table)


def test_claim_table_accepts_primary_source_evidence_per_field():
    evidence = {
        "models": [
            {
                "model_id": "Qwythos-9B-Claude-Mythos-5-1M",
                "claims": {
                    "model_identity": {
                        "status": "verified_primary_source",
                        "value": "Qwythos-9B-Claude-Mythos-5-1M",
                        "source_url": "https://example.test/model-card",
                        "retrieved_at": "2026-07-09",
                    },
                    "primary_model_card_url": {
                        "status": "verified_primary_source",
                        "value": "https://example.test/model-card",
                        "source_url": "https://example.test/model-card",
                        "retrieved_at": "2026-07-09",
                    },
                },
            }
        ]
    }

    table = build_claim_table(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        evidence=evidence,
    )

    row = table["model_rows"][0]
    assert row["overall_claim_status"] == "partially_verified"
    assert row["primary_model_card_url"] == "https://example.test/model-card"
    assert table["summary"]["verified_primary_source_fields"] == 2


def test_render_markdown_lists_models_and_guards():
    table = build_claim_table(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
    )

    markdown = render_markdown(table)

    assert "# Model-card claim table" in markdown
    assert "Qwythos-9B-Claude-Mythos-5-1M" in markdown
    assert "Network fetch: `false`" in markdown
    assert "must not call providers" in markdown
