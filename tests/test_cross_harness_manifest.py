import pytest

from harness.cross_harness_manifest import build_manifest, render_markdown


def _task_set():
    return {
        "schema": "harness.agentic-task-set/v1",
        "task_set_id": "sample_tasks",
        "tasks": [
            {
                "id": "agt-001",
                "lane": "agentic_tool_workflows",
                "difficulty": "focused",
                "prompt": "Run the same task across harnesses.",
                "required_inputs": ["contract.json"],
                "expected_artifacts": ["receipt.json"],
                "scoring_focus": ["quality", "reproducibility"],
                "must_not": ["run providers during manifest generation"],
            }
        ],
    }


def _contract():
    return {
        "schema": "harness.cross-harness-adapter-contract/v1",
        "contract_id": "sample_cross_harness",
        "global_invariants": ["same prompt hash"],
        "planned_scorecard_schema": "harness.cross-harness-task-scorecard/v1",
        "planned_run_receipt_schema": "harness.cross-harness-run-receipt/v1",
        "provider_roles": [
            {
                "provider_role": "codex_harness",
                "harness_id": "codex",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
            {
                "provider_role": "flywheel_harness",
                "harness_id": "flywheel",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
        ],
        "scorecard_row_contract": {
            "required_metrics": ["task_completion", "quality", "reproducibility"]
        },
        "comparability_checks": ["same raw_prompt_sha256"],
    }


def test_cross_harness_manifest_expands_same_prompt_across_provider_roles():
    manifest = build_manifest(_task_set(), _contract(), provider_roles=["codex_harness", "flywheel_harness"])

    assert manifest["schema"] == "harness.cross-harness-manifest/v1"
    assert manifest["status"] == "planned_not_executed"
    assert manifest["benchmark_id"] == "cross_harness_reproducibility_matrix"
    assert manifest["summary"]["provider_execution"] is False
    assert manifest["summary"]["endpoint_probe"] is False
    assert manifest["summary"]["benchmark_execution"] is False
    assert manifest["task_count"] == 1
    assert len(manifest["dry_scorecard_rows"]) == 2
    assert {row["provider_role"] for row in manifest["dry_scorecard_rows"]} == {
        "codex_harness",
        "flywheel_harness",
    }
    assert len({row["raw_prompt_sha256"] for row in manifest["dry_scorecard_rows"]}) == 1
    assert all(row["failure_class"] == "not_executed" for row in manifest["dry_scorecard_rows"])


def test_cross_harness_manifest_rejects_unknown_provider_role():
    with pytest.raises(ValueError, match="unknown cross-harness provider roles"):
        build_manifest(_task_set(), _contract(), provider_roles=["missing_provider"])


def test_cross_harness_manifest_markdown_declares_non_execution():
    markdown = render_markdown(build_manifest(_task_set(), _contract(), provider_roles=["codex_harness"]))

    assert "# Cross-harness manifest" in markdown
    assert "Provider execution: `false`" in markdown
    assert "codex_harness" in markdown
