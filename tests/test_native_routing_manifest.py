import json
from pathlib import Path

import pytest

from harness.native_routing_manifest import (
    build_manifest,
    render_case_projection,
    render_markdown,
)
from scripts.run_native_routing_manifest import main as run_manifest


def _demo_doc():
    return {
        "schema": "harness.native-routing-task-family-set/v1",
        "task_set_id": "native_routing_demo",
        "dataset_status": "demo_fixture_not_180_case_benchmark",
        "modality_scope": {
            "current_manifest_scope": "text/account-state/action-log support and workflow routing only",
            "does_not_test": ["genuine_images", "ui_frames", "ocr_extraction", "video_event_streams"],
        },
        "split_policy": {
            "split_id": "native-routing-demo-split",
            "ordering_claim": "ordering only; not independent preregistration",
        },
        "execution_denominator_schema": {
            "required_per_case_attempt_fields": [
                "host_region_or_locality",
                "local_hardware",
                "cache_hit_miss",
                "concurrency_policy",
                "option_count",
                "retries_attempted",
                "p50_ms",
                "p95_ms",
                "provider_cost_or_null",
                "local_compute_cost_or_null",
                "null_reason_for_unavailable_cost_or_tokens",
            ],
        },
        "candidate_arms": [
            {
                "arm_id": "arm_rules_001",
                "arm_class": "rules",
                "pin_status": "pinned_non_model_baseline",
                "adapter_mode": "policy_table_single_choice",
                "execution_gate": "planned_only",
            },
            {
                "arm_id": "arm_slm_choice_001",
                "arm_class": "SLM",
                "pin_status": "pin_required_before_execution",
                "adapter_mode": "constrained_single_choice",
                "execution_gate": "blocked_until_pinned",
            },
        ],
        "task_families": [
            {
                "family_id": "f_dev_a1",
                "private_human_label": "permission gate",
                "semantic_family_tags": ["permission-gate", "development"],
                "split_role": "development",
                "target_cases": 1,
            },
            {
                "family_id": "f_eval_b2",
                "private_human_label": "workflow utility",
                "semantic_family_tags": ["workflow-utility", "unseen"],
                "split_role": "unseen_family_evaluation",
                "target_cases": 1,
            },
        ],
        "cases": [
            {
                "case_id": "c_001",
                "family_id": "f_dev_a1",
                "case_group_id": "g_001",
                "split_role": "development",
                "scenario_state": {
                    "redacted_user_text": "Customer asks for an account action.",
                    "redacted_account_state": "Plan allows read-only support.",
                    "redacted_action_log": "No prior action is recorded.",
                },
                "option_set": [
                    {"option_id": "o_01", "label": "Ask a follow-up question"},
                    {"option_id": "o_02", "label": "Decline the unavailable action"},
                ],
                "policy_excerpt_ids": ["p_001"],
                "hidden_leakage_sentinels": ["AUTH-SENTINEL"],
                "hidden_authority_refs": {
                    "raw_private_authority": "authority://AUTH-SENTINEL/permission"
                },
                "hard_policy_contract": {
                    "labels_are": "constraints_only",
                    "expected_option_id": "o_02",
                    "hidden_expected_fields": ["AUTH-SENTINEL"],
                },
                "workflow_utility_contract": {
                    "status": "not_primary",
                    "no_optimal_gold": True,
                    "measured": False,
                },
            },
            {
                "case_id": "c_002",
                "family_id": "f_eval_b2",
                "case_group_id": "g_002",
                "split_role": "unseen_family_evaluation",
                "scenario_state": {
                    "redacted_user_text": "Customer asks which support path fits a bounded task.",
                    "redacted_account_state": "All required context is present.",
                    "redacted_action_log": "No conflicting action is recorded.",
                },
                "option_set": [
                    {"option_id": "o_01", "label": "Use the rules baseline"},
                    {"option_id": "o_02", "label": "Escalate to a pinned model arm"},
                ],
                "policy_excerpt_ids": ["p_002"],
                "hidden_leakage_sentinels": ["UTILITY-SENTINEL"],
                "hidden_authority_refs": {
                    "raw_private_authority": "authority://UTILITY-SENTINEL/workflow"
                },
                "hard_policy_contract": {
                    "labels_are": "constraints_only",
                    "expected_option_id": "o_01",
                },
                "workflow_utility_contract": {
                    "status": "planned_unmeasured",
                    "no_optimal_gold": True,
                    "measured": False,
                    "reported_label": "best_observed_under_this_denominator",
                },
            },
        ],
    }


def test_build_manifest_renders_planned_rows_without_execution():
    manifest = build_manifest(_demo_doc(), source_path="demo.json", source_sha256="abc")

    assert manifest["schema"] == "harness.native-routing-task-family-manifest/v1"
    assert manifest["status"] == "planned_not_executed"
    assert manifest["summary"]["model_execution"] is False
    assert manifest["summary"]["benchmark_execution"] is False
    assert manifest["summary"]["total_cases"] == 2
    assert manifest["summary"]["workflow_utility_measured"] is False
    assert {row["case_id"] for row in manifest["case_rows"]} == {"c_001", "c_002"}
    assert all(row["workflow_utility_status"] != "measured" for row in manifest["case_rows"])


def test_projection_omits_private_family_labels_and_cache_keys():
    doc = _demo_doc()
    projection = render_case_projection(doc, doc["cases"][0], doc["candidate_arms"][0])
    visible = (
        projection["model_visible_prompt"]
        + json.dumps(projection["model_visible_features"], sort_keys=True)
        + json.dumps(projection["cache_key_material"], sort_keys=True)
    )

    assert "permission gate" not in visible
    assert "AUTH-SENTINEL" not in visible
    assert "development" not in visible
    assert "f_dev_a1" not in visible
    assert projection["hidden_authority_manifest"]["hidden_leakage_sentinels"] == ["AUTH-SENTINEL"]


def test_projection_fails_closed_when_hidden_sentinel_reaches_visible_text():
    doc = _demo_doc()
    doc["cases"][0]["scenario_state"]["redacted_user_text"] = "AUTH-SENTINEL leaked"

    with pytest.raises(ValueError, match="leakage"):
        render_case_projection(doc, doc["cases"][0], doc["candidate_arms"][0])


def test_validator_rejects_workflow_utility_claimed_as_gold():
    doc = _demo_doc()
    doc["cases"][1]["workflow_utility_contract"]["no_optimal_gold"] = False

    with pytest.raises(ValueError, match="no optimal gold"):
        build_manifest(doc)


def test_validator_rejects_semantic_opaque_ids_before_projection():
    doc = _demo_doc()
    doc["cases"][0]["case_id"] = "c_permission_gate"
    doc["cases"][0]["case_group_id"] = "g_permission_gate"
    doc["cases"][0]["policy_excerpt_ids"] = ["p_permission_gate"]
    doc["cases"][0]["option_set"][0]["option_id"] = "o_permission_gate"

    with pytest.raises(ValueError, match="opaque"):
        render_case_projection(doc, doc["cases"][0], doc["candidate_arms"][0])


def test_projection_fails_on_cross_family_semantic_tag_leakage():
    doc = _demo_doc()
    doc["cases"][0]["scenario_state"]["redacted_user_text"] = "workflow-utility leaked"

    with pytest.raises(ValueError, match="leakage"):
        render_case_projection(doc, doc["cases"][0], doc["candidate_arms"][0])


def test_validator_rejects_two_case_fixture_relabelled_complete():
    doc = _demo_doc()
    doc["dataset_status"] = "complete_180_case_benchmark"

    with pytest.raises(ValueError, match="demo"):
        build_manifest(doc)


def test_markdown_declares_demo_scope_and_no_execution():
    markdown = render_markdown(build_manifest(_demo_doc()))

    assert "demo_fixture_not_180_case_benchmark" in markdown
    assert "Model execution: `false`" in markdown
    assert "Workflow utility measured: `false`" in markdown


def test_cli_writes_planned_manifest_and_projection_files(tmp_path):
    task_set = tmp_path / "demo.json"
    out = tmp_path / "manifest.json"
    markdown = tmp_path / "manifest.md"
    projections = tmp_path / "projections"
    task_set.write_text(json.dumps(_demo_doc()), encoding="utf-8")

    assert run_manifest([
        "--task-set", str(task_set),
        "--out", str(out),
        "--markdown-out", str(markdown),
        "--projection-dir", str(projections),
    ]) == 0

    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["status"] == "planned_not_executed"
    assert manifest["summary"]["model_execution"] is False
    assert markdown.read_text(encoding="utf-8").startswith("# Native routing task-family manifest")
    projection_text = (projections / "c_001" / "arm_rules_001" / "model_visible_prompt.txt").read_text(encoding="utf-8")
    cache_text = (projections / "c_001" / "arm_rules_001" / "cache_key_material.json").read_text(encoding="utf-8")
    assert "AUTH-SENTINEL" not in projection_text
    assert "permission-gate" not in cache_text
