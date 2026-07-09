import pytest

from harness.agentic_task_manifest import build_manifest, render_markdown


def _task_set():
    return {
        "schema": "harness.agentic-task-set/v1",
        "task_set_id": "sample_tasks",
        "metrics": [{"id": "quality", "weight": 1.0}],
        "lanes": [{"id": "agentic_tool_workflows"}],
        "global_rules": {"artifact_required": True},
        "tasks": [
            {
                "id": "agt-001",
                "lane": "agentic_tool_workflows",
                "difficulty": "focused",
                "prompt": "Prepare a manifest-only task.",
                "required_inputs": ["C:/dev/local-model/benchmarks/agentic-task-set-v1.json"],
                "expected_artifacts": ["manifest.json"],
                "scoring_focus": ["quality", "reproducibility"],
                "must_not": ["run providers"],
            }
        ],
    }


def _adapter():
    return {
        "schema": "harness.agentic-task-set-adapter/v1",
        "adapter_id": "sample_adapter",
        "planned_scorecard_schema": "harness.agentic-task-scorecard/v1",
        "task_benchmark_map": {"agt-001": "closed_loop_agentic_gauntlet"},
        "non_execution_guards": ["Do not execute providers."],
    }


def test_manifest_expands_task_rows_without_execution():
    manifest = build_manifest(_task_set(), _adapter(), provider_roles=["dry"])

    assert manifest["schema"] == "harness.agentic-task-manifest/v1"
    assert manifest["status"] == "planned_not_executed"
    assert manifest["task_count"] == 1
    assert manifest["task_rows"][0]["coverage_unit"] == "agt-001"
    assert manifest["task_rows"][0]["benchmark_id"] == "closed_loop_agentic_gauntlet"
    assert manifest["summary"]["provider_execution"] is False
    assert manifest["summary"]["endpoint_probe"] is False
    assert manifest["summary"]["benchmark_execution"] is False


def test_manifest_emits_dry_scorecard_rows_with_prompt_hashes():
    manifest = build_manifest(_task_set(), _adapter(), provider_roles=["dry", "codex_harness"])
    rows = manifest["dry_scorecard_rows"]

    assert len(rows) == 2
    assert {row["provider_role"] for row in rows} == {"dry", "codex_harness"}
    assert all(row["execution_mode"] == "manifest_only" for row in rows)
    assert all(row["status"] == "planned" for row in rows)
    assert rows[0]["raw_prompt_sha256"] == manifest["task_rows"][0]["raw_prompt_sha256"]
    assert rows[0]["failure_class"] == "not_executed"


def test_manifest_rejects_missing_task_mapping():
    adapter = _adapter()
    adapter["task_benchmark_map"] = {}

    with pytest.raises(ValueError, match="missing adapter benchmark mapping"):
        build_manifest(_task_set(), adapter)


def test_manifest_markdown_declares_non_execution():
    markdown = render_markdown(build_manifest(_task_set(), _adapter()))

    assert "# Agentic task manifest" in markdown
    assert "Provider execution: `false`" in markdown
    assert "closed_loop_agentic_gauntlet" in markdown
