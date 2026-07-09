import json

from scripts.run_embodied_realtime_multimodal_plan import (
    build_plan,
    parse_int_csv,
    render_markdown,
)


def contract_fixture():
    return {
        "schema": "harness.benchmark-contract/v1",
        "benchmark_id": "embodied_realtime_multimodal_pressure",
        "dataset_lanes": ["embodied_realtime_multimodal", "local_resource_pressure"],
        "pressure_variables": ["real-time-latency", "sensor-token-stream"],
        "source_feedback": {"model_leads_unverified": ["Qwythos-9B-Claude-Mythos-5-1M"]},
        "probe_groups": [
            {
                "id": "tiny_robotics_latency",
                "question": "Can a small model stay useful under a realtime budget?",
                "measurements": ["first_token_ms", "task_success"],
            },
            {
                "id": "affective_drift_probe",
                "question": "Does benign companion framing induce possessive drift?",
                "measurements": ["possessive_affect_rate"],
            },
        ],
    }


def test_parse_int_csv_defaults_when_empty():
    assert parse_int_csv("") == [250, 500, 1000]
    assert parse_int_csv("100, 250") == [100, 250]


def test_build_plan_expands_probe_provider_budget_rows():
    plan = build_plan(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        provider_roles=["dry_fixture", "codex"],
        latency_budgets_ms=[250, 500],
        artifact_dir="C:/tmp/embodied",
        run_id="run_123",
    )

    assert plan["schema"] == "harness.embodied-realtime-multimodal/v1"
    assert plan["summary"]["planned_probe_rows"] == 8
    assert plan["summary"]["planned_scorecard_rows"] == 8
    assert plan["model_leads_unverified"] == ["Qwythos-9B-Claude-Mythos-5-1M"]
    assert plan["probe_rows"][0]["execution_required_for_score"] is True
    assert plan["dry_scorecard_rows"][0]["failure_class"] == "not_executed"
    assert plan["dry_scorecard_rows"][0]["receipt_hash"] == ""
    assert "tiny_model_robotics_latency" in plan["dry_scorecard_rows"][0]["coverage_unit"]
    json.dumps(plan)


def test_render_markdown_lists_probe_rows_and_limitations():
    plan = build_plan(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        provider_roles=["dry_fixture"],
        latency_budgets_ms=[250],
        artifact_dir="C:/tmp/embodied",
    )

    markdown = render_markdown(plan)

    assert "# Embodied realtime multimodal benchmark plan" in markdown
    assert "tiny_robotics_latency" in markdown
    assert "Dry scorecard rows must not be counted" in markdown
