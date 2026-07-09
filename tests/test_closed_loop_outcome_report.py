import json

from scripts.run_closed_loop_outcome_report import (
    build_outcome,
    conclusion,
    extract_child_artifact_summaries,
    find_seed_report_in_store,
    render_markdown,
)
from harness.file_backed_store import FileBackedHarnessStore


def test_conclusion_marks_dry_plan_as_plan_only():
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "dry_plan": True,
        "summary": {"steps": 2},
    }

    result = conclusion(report)

    assert result["verdict"] == "OUTCOME_PLAN_ONLY"
    assert "No benchmark execution evidence" in result["claim"]


def test_conclusion_marks_failed_step_as_partial():
    report = {
        "dry_plan": False,
        "summary": {"failed_steps": 1, "timeout_steps": 0},
    }

    result = conclusion(report)

    assert result["verdict"] == "OUTCOME_PARTIAL"


def test_build_outcome_preserves_step_observations():
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_123",
        "dry_plan": False,
        "planned_steps": [{"step_id": "endpoint_auth_status"}],
        "results": [
            {
                "step_id": "endpoint_auth_status",
                "status": "ok",
                "returncode": 0,
                "elapsed_ms": 10,
                "expected_artifacts": ["auth.json"],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    assert outcome["schema"] == "harness.closed-loop-outcome/v1"
    assert outcome["run_id"] == "run_123"
    assert outcome["conclusion"]["verdict"] == "OUTCOME_RECORDED"
    assert outcome["observations"]["observed_steps"][0]["step_id"] == "endpoint_auth_status"


def test_render_markdown_separates_unknowns_and_next_checks():
    outcome = build_outcome(
        {
            "schema": "harness.closed-loop-benchmark-seed/v1",
            "run_id": "dry_plan",
            "dry_plan": True,
            "planned_steps": [{"step_id": "m7_source_mined", "expected_artifacts": ["m7.json"]}],
            "summary": {"steps": 1},
        },
        source_report_path="plan.json",
    )

    markdown = render_markdown(outcome)

    assert "# Closed-loop benchmark experimental outcome" in markdown
    assert "## Unknowns" in markdown
    assert "## Next checks" in markdown
    assert "m7_source_mined" in markdown


def test_extract_child_artifact_summaries_reads_m7_source_mined_comparison(tmp_path):
    scorecard = tmp_path / "m7_source.json"
    scorecard.write_text(json.dumps({
        "schema": "m7-source-mined-scorecard/v1",
        "summary": {
            "comparison": {
                "available": True,
                "flywheel_provider": "serve",
                "codex_provider": "codex",
                "pass_rate_delta_flywheel_minus_codex": 1.0,
            }
        },
        "backend_rows": [
            {
                "provider": "serve",
                "backend_name": "serve",
                "live": True,
                "operational": True,
                "pass_rate": 1.0,
                "mean_latency_ms": 10,
                "aggregate_metrics": {
                    "mean_quality_score": 0.8,
                    "failure_class_counts": {},
                },
            },
            {
                "provider": "codex",
                "backend_name": "codex",
                "live": True,
                "operational": True,
                "pass_rate": 0.0,
                "mean_latency_ms": 20,
                "aggregate_metrics": {
                    "mean_quality_score": 0.1,
                    "failure_class_counts": {"timeout": 1},
                },
            },
        ],
    }), encoding="utf-8")
    report = {
        "results": [
            {
                "step_id": "m7_source_mined",
                "expected_artifacts": [str(scorecard)],
            }
        ]
    }

    summaries = extract_child_artifact_summaries(report)

    assert summaries[0]["kind"] == "m7_source_mined"
    assert summaries[0]["comparison"]["flywheel_provider"] == "serve"
    assert summaries[0]["provider_metrics"][1]["provider"] == "codex"


def test_build_outcome_includes_unisonai_provider_metrics(tmp_path):
    matrix = tmp_path / "unisonai.json"
    matrix.write_text(json.dumps({
        "schema": "unisonai.stateful-provider-matrix/v1",
        "summary": {"failed_rows": 1, "skipped_rows": 1},
        "rows": [
            {
                "provider": "dry",
                "live": False,
                "operational": True,
                "passed": True,
                "pass_rate": 1.0,
                "failure_class": "",
                "action_count": 8,
            },
            {
                "provider": "codex",
                "live": True,
                "operational": False,
                "passed": False,
                "pass_rate": 0.0,
                "failure_class": "malformed_action_json",
                "action_count": 0,
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_123",
        "dry_plan": False,
        "planned_steps": [{"step_id": "unisonai_stateful_provider_matrix"}],
        "results": [
            {
                "step_id": "unisonai_stateful_provider_matrix",
                "status": "ok",
                "expected_artifacts": [str(matrix)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["benchmark_signals"]
    assert signals["scorecard_count"] == 1
    assert signals["providers_observed"] == ["codex", "dry"]
    child = outcome["observations"]["child_artifacts"][0]
    assert child["provider_metrics"][1]["failure_class"] == "malformed_action_json"


def test_build_outcome_includes_classifier_friction_metrics(tmp_path):
    classifier = tmp_path / "classifier_friction_benchmark.json"
    classifier.write_text(json.dumps({
        "schema": "classifier-friction-benchmark/v1",
        "provider_native_safety_note": "provider-native guardrails remain active",
        "tasks": ["enterprise_vuln_triage_safe"],
        "modes": ["guardrail_on", "accountability_first"],
        "summary": {
            "rows": [
                {
                    "provider": "codex",
                    "mode": "guardrail_on",
                    "cases": 1,
                    "pass_rate": 0.0,
                    "mean_quality_score": 0.2,
                    "mean_latency_ms": 100,
                    "refusal_rate": 1.0,
                    "unnecessary_refusal_rate": 1.0,
                    "provider_native_guardrail_observed_rate": 0.0,
                    "error_rate": 0.0,
                },
                {
                    "provider": "codex",
                    "mode": "accountability_first",
                    "cases": 1,
                    "pass_rate": 1.0,
                    "mean_quality_score": 0.8,
                    "mean_latency_ms": 90,
                    "refusal_rate": 0.0,
                    "unnecessary_refusal_rate": 0.0,
                    "provider_native_guardrail_observed_rate": 0.0,
                    "error_rate": 0.0,
                },
            ]
        },
        "deltas": [
            {
                "provider": "codex",
                "comparison": "accountability_first_minus_guardrail_off",
                "quality_delta": 0.4,
            }
        ],
        "skipped": [],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_classifier",
        "dry_plan": False,
        "results": [
            {
                "step_id": "classifier_friction",
                "status": "ok",
                "expected_artifacts": [str(classifier)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["benchmark_signals"]
    assert signals["scorecard_count"] == 1
    assert signals["providers_observed"] == ["codex"]
    assert signals["classifier_modes_observed"] == ["accountability_first", "guardrail_on"]
    assert signals["classifier_delta_count"] == 1
    child = outcome["observations"]["child_artifacts"][0]
    assert child["kind"] == "classifier_friction_accountability"
    assert child["provider_metrics"][0]["mode"] == "guardrail_on"


def test_build_outcome_includes_cross_harness_manifest_signals(tmp_path):
    manifest = tmp_path / "cross_harness_manifest.json"
    manifest.write_text(json.dumps({
        "schema": "harness.cross-harness-manifest/v1",
        "task_count": 1,
        "benchmark_ids": ["cross_harness_reproducibility_matrix"],
        "dataset_lanes": ["cross_harness_reproducibility"],
        "provider_roles": ["codex_harness", "flywheel_harness"],
        "task_rows": [
            {
                "task_id": "agt-001",
                "coverage_unit": "agt-001",
                "raw_prompt_sha256": "abcdef1234567890",
            }
        ],
        "dry_scorecard_rows": [
            {"provider_role": "codex_harness"},
            {"provider_role": "flywheel_harness"},
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_cross",
        "dry_plan": False,
        "results": [
            {
                "step_id": "cross_harness_manifest",
                "status": "ok",
                "expected_artifacts": [str(manifest)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["cross_harness_manifest_signals"]
    assert signals["manifest_artifacts"] == 1
    assert signals["task_count"] == 1
    assert signals["planned_scorecard_rows"] == 2
    assert signals["provider_roles"] == ["codex_harness", "flywheel_harness"]


def test_build_outcome_includes_adapter_runtime_signals(tmp_path):
    matrix = tmp_path / "adapter_runtime_matrix.json"
    matrix.write_text(json.dumps({
        "schema": "harness.adapter-runtime-matrix/v1",
        "summary": {
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
            "token_store_read": False,
        },
        "runtime_rows": [
            {
                "provider_role": "codex_harness",
                "harness_id": "codex",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "manifest_ready": True,
                "focused_run_ready": True,
                "endpoint_profile_ready": True,
                "auth_ready": True,
                "blocking_gates": [],
            },
            {
                "provider_role": "local_14b",
                "harness_id": "local_endpoint",
                "target_model": "14B",
                "adapter_state": "needs_endpoint_profile_and_gate",
                "manifest_ready": True,
                "focused_run_ready": False,
                "endpoint_profile_ready": True,
                "auth_ready": True,
                "blocking_gates": ["endpoint_gate"],
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_adapter_runtime",
        "dry_plan": False,
        "results": [
            {
                "step_id": "adapter_runtime_matrix",
                "status": "ok",
                "expected_artifacts": [str(matrix)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["adapter_runtime_signals"]
    assert signals["matrix_artifacts"] == 1
    assert signals["runtime_rows"] == 2
    assert signals["manifest_ready_roles"] == ["codex_harness", "local_14b"]
    assert signals["focused_run_ready_roles"] == ["codex_harness"]
    assert signals["blocking_gate_counts"]["endpoint_gate"] == 1
    assert signals["provider_execution_observed"] is False
    markdown = render_markdown(outcome)
    assert "## Adapter runtime signals" in markdown


def test_build_outcome_includes_forum_route_signals(tmp_path):
    routes = tmp_path / "forum_route_receipts.json"
    routes.write_text(json.dumps({
        "schema": "harness.forum-route-receipts/v1",
        "summary": {
            "route_count": 1,
            "observed_route_frames": 1,
            "route_text_only": 0,
            "escalation_count": 1,
            "mean_observed_confidence": 0.1459,
        },
        "routes": [
            {
                "route_id": "route-001",
                "observation_status": "observed_route_frame",
                "observed": True,
                "observed_decided": "",
                "observed_confidence": 0.1459,
                "observed_needs_escalation": True,
                "observed_domain": "operator-platform",
                "observed_intent": "coordinate",
                "observed_posture": "operator",
                "observed_proof_lane": "synthesize",
                "observed_domain_lane": "frontier-foundry",
                "provider_execution_observed": False,
                "endpoint_probe_observed": False,
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_forum_routes",
        "dry_plan": False,
        "results": [
            {
                "step_id": "forum_route_receipts",
                "status": "ok",
                "expected_artifacts": [str(routes)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["forum_route_signals"]
    assert signals["route_artifacts"] == 1
    assert signals["route_count"] == 1
    assert signals["observed_route_frames"] == 1
    assert signals["escalation_count"] == 1
    assert signals["mean_observed_confidence"] == 0.1459
    assert signals["domains"] == ["operator-platform"]
    assert signals["proof_lanes"] == ["synthesize"]
    markdown = render_markdown(outcome)
    assert "## Forum route signals" in markdown


def test_build_outcome_includes_mcp_tool_health_signals(tmp_path):
    health = tmp_path / "mcp_tool_health.json"
    health.write_text(json.dumps({
        "schema": "harness.mcp-tool-health/v1",
        "summary": {
            "tools": 3,
            "roots_existing": 3,
            "observed_tools": 3,
            "healthy_observed_tools": 2,
            "degraded_observed_tools": 1,
            "configured_unobserved_tools": 0,
            "missing_roots": 0,
            "verdict_counts": {"OBSERVED_HEALTHY": 2, "OBSERVED_DEGRADED": 1},
        },
        "tools": [
            {
                "tool": "index",
                "role": "structure-context",
                "root_exists": True,
                "observed": True,
                "observed_status": "TRANSPORT_CLOSED",
                "observed_error_code": "transport_closed",
                "verdict": "OBSERVED_DEGRADED",
                "provider_execution_observed": False,
                "endpoint_probe_observed": False,
            },
            {
                "tool": "forum",
                "role": "orchestration-routing",
                "root_exists": True,
                "observed": True,
                "observed_status": "MATCH",
                "observed_error_code": "",
                "verdict": "OBSERVED_HEALTHY",
                "provider_execution_observed": False,
                "endpoint_probe_observed": False,
            },
            {
                "tool": "telos",
                "role": "shared-room-reconciliation",
                "root_exists": True,
                "observed": True,
                "observed_status": "MATCH",
                "observed_error_code": "",
                "verdict": "OBSERVED_HEALTHY",
                "provider_execution_observed": False,
                "endpoint_probe_observed": False,
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_mcp_health",
        "dry_plan": False,
        "results": [
            {
                "step_id": "mcp_tool_health",
                "status": "ok",
                "expected_artifacts": [str(health)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["mcp_tool_health_signals"]
    assert signals["health_artifacts"] == 1
    assert signals["tools"] == 3
    assert signals["healthy_observed_tools"] == 2
    assert signals["degraded_observed_tools"] == 1
    assert signals["healthy_tools"] == ["forum", "telos"]
    assert signals["degraded_tools"] == ["index"]
    markdown = render_markdown(outcome)
    assert "## MCP tool health signals" in markdown


def test_build_outcome_includes_schematic_drift_signals(tmp_path):
    drift = tmp_path / "schematic_drift_check.json"
    drift.write_text(json.dumps({
        "schema": "harness.schematic-drift-check/v1",
        "verdict": "SCHEMATIC_DRIFT",
        "summary": {
            "missing_nodes": 1,
            "missing_edges": 2,
            "missing_files": 0,
            "stale_phrases": 1,
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_drift",
        "dry_plan": False,
        "results": [
            {
                "step_id": "schematic_drift_check",
                "status": "ok",
                "expected_artifacts": [str(drift)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["schematic_drift_signals"]
    assert signals["drift_artifacts"] == 1
    assert signals["verdicts"] == ["SCHEMATIC_DRIFT"]
    assert signals["missing_nodes"] == 1
    assert signals["missing_edges"] == 2
    assert signals["stale_phrases"] == 1


def test_build_outcome_includes_context_inventory_signals(tmp_path):
    inventory = tmp_path / "context_inventory.json"
    inventory.write_text(json.dumps({
        "schema": "harness.context-inventory/v1",
        "summary": {
            "roots": 2,
            "existing_roots": 1,
            "entries": 3,
            "files": 2,
            "directories": 1,
            "sensitive_name_entries": 1,
            "label_counts": {
                "benchmark_artifact": 1,
                "session_context": 1,
                "scratch_temp": 2,
                "sensitive_name": 1,
            },
        },
        "roots": [
            {
                "root": "C:/tmp",
                "exists": True,
                "observed_entries": 3,
                "truncated": False,
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_context",
        "dry_plan": False,
        "results": [
            {
                "step_id": "context_inventory",
                "status": "ok",
                "expected_artifacts": [str(inventory)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["context_signals"]
    assert signals["inventory_count"] == 1
    assert signals["entries"] == 3
    assert signals["sensitive_name_entries"] == 1
    assert signals["label_counts"]["scratch_temp"] == 2
    markdown = render_markdown(outcome)
    assert "## Context signals" in markdown


def test_build_outcome_includes_tool_readiness_signals(tmp_path):
    readiness = tmp_path / "tool_readiness.json"
    readiness.write_text(json.dumps({
        "schema": "harness.tool-readiness/v1",
        "summary": {
            "tools": 3,
            "existing_tools": 3,
            "enterprise_ready_tools": 0,
            "mean_score": 0.5,
            "verdict_counts": {"PROTOTYPE_WITH_GAPS": 3},
        },
        "tools": [
            {
                "tool": "mneme",
                "root_exists": True,
                "enterprise_ready": False,
                "verdict": "PROTOTYPE_WITH_GAPS",
                "score": 0.5,
                "categories": {
                    "core": {"score": 1.0},
                    "enterprise": {"score": 0.0},
                    "integration": {"score": 0.5},
                },
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_tools",
        "dry_plan": False,
        "results": [
            {
                "step_id": "tool_readiness",
                "status": "ok",
                "expected_artifacts": [str(readiness)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["tool_readiness_signals"]
    assert signals["readiness_artifacts"] == 1
    assert signals["tools_observed"] == ["mneme"]
    assert signals["verdict_counts"]["PROTOTYPE_WITH_GAPS"] == 1
    markdown = render_markdown(outcome)
    assert "## Tool readiness signals" in markdown


def test_build_outcome_includes_tool_hardening_signals(tmp_path):
    plan = tmp_path / "tool_hardening_plan.json"
    plan.write_text(json.dumps({
        "schema": "harness.tool-hardening-plan/v1",
        "summary": {
            "actions": 2,
            "release_gates": 4,
            "passed_release_gates": 2,
            "priority_counts": {"P1": 1, "P2": 1},
            "owner_counts": {"release-engineering": 1, "platform-integration": 1},
        },
        "actions": [
            {
                "tool": "relay",
                "priority": "P2",
                "category": "enterprise",
                "owner": "release-engineering",
                "path": "SECURITY.md",
            },
            {
                "tool": "relay",
                "priority": "P1",
                "category": "integration",
                "owner": "platform-integration",
                "path": "serve.py",
            },
        ],
        "release_gates": [
            {"tool": "relay", "gate_id": "core_static_complete", "category": "core", "passed": True},
            {"tool": "relay", "gate_id": "enterprise_static_complete", "category": "enterprise", "passed": False},
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_hardening",
        "dry_plan": False,
        "results": [
            {
                "step_id": "tool_hardening_plan",
                "status": "ok",
                "expected_artifacts": [str(plan)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["tool_hardening_signals"]
    assert signals["plan_artifacts"] == 1
    assert signals["actions"] == 2
    assert signals["priority_counts"]["P1"] == 1
    assert signals["owner_counts"]["platform-integration"] == 1
    markdown = render_markdown(outcome)
    assert "## Tool hardening signals" in markdown


def test_build_outcome_includes_model_release_signals(tmp_path):
    readiness = tmp_path / "model_release_readiness.json"
    readiness.write_text(json.dumps({
        "schema": "harness.model-release-readiness/v1",
        "summary": {
            "models": 2,
            "existing_models": 1,
            "models_with_weights": 1,
            "release_ready_models": 0,
            "benchmark_artifact_matches": 1,
            "mean_release_doc_score": 0.5,
            "verdict_counts": {"MODEL_ARTIFACTS_WITH_RELEASE_GAPS": 1},
        },
        "models": [
            {
                "model": "14B",
                "root_exists": True,
                "enterprise_release_ready": False,
                "verdict": "MODEL_ARTIFACTS_WITH_RELEASE_GAPS",
                "weight_file_count": 1,
                "weight_total_size_bytes": 123,
                "release_doc_score": 0.5,
                "endpoint_profile_count": 1,
                "endpoint_gate_row_count": 1,
                "endpoint_gate_generation_ok_count": 1,
                "benchmark_artifact_count": 1,
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_models",
        "dry_plan": False,
        "results": [
            {
                "step_id": "model_release_readiness",
                "status": "ok",
                "expected_artifacts": [str(readiness)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["model_release_signals"]
    assert signals["release_artifacts"] == 1
    assert signals["models_observed"] == ["14B"]
    assert signals["models_with_weights"] == 1
    assert signals["endpoint_profile_matches"] == 1
    assert signals["endpoint_gate_rows"] == 1
    assert signals["endpoint_gate_generation_ok"] == 1
    assert signals["benchmark_artifact_matches"] == 1
    markdown = render_markdown(outcome)
    assert "## Model release signals" in markdown


def test_build_outcome_includes_model_publish_plan_signals(tmp_path):
    publish = tmp_path / "model_publish_plan.json"
    publish.write_text(json.dumps({
        "schema": "harness.model-publish-plan/v1",
        "summary": {
            "models": 2,
            "ready_to_stage_models": 1,
            "do_not_publish_models": 1,
            "candidate_names": ["Flywheel-Local-Coder-14B", "Flywheel-Local-Coder-32B"],
        },
        "models": [
            {
                "model": "14B",
                "candidate_name": "Flywheel-Local-Coder-14B",
                "candidate_slug": "flywheel-local-coder-14b",
                "publish_status": "READY_TO_STAGE",
                "blockers": [],
                "actions": [],
            },
            {
                "model": "32B",
                "candidate_name": "Flywheel-Local-Coder-32B",
                "candidate_slug": "flywheel-local-coder-32b",
                "publish_status": "DO_NOT_PUBLISH",
                "blockers": ["No endpoint generation gate has passed."],
                "actions": [{"action": "Run endpoint gate"}],
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_publish",
        "dry_plan": False,
        "results": [
            {
                "step_id": "model_publish_plan",
                "status": "ok",
                "expected_artifacts": [str(publish)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["model_publish_signals"]
    assert signals["publish_plan_artifacts"] == 1
    assert signals["candidate_names"] == ["Flywheel-Local-Coder-14B", "Flywheel-Local-Coder-32B"]
    assert signals["ready_to_stage_models"] == 1
    assert signals["do_not_publish_models"] == 1
    assert signals["blockers"] == 1
    markdown = render_markdown(outcome)
    assert "## Model publish signals" in markdown


def test_build_outcome_includes_model_endpoint_profile_signals(tmp_path):
    endpoints = tmp_path / "model_endpoint_profiles.json"
    endpoints.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "summary": {"profiles": 2},
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "root_exists": True,
                "supports_agentic_workflow": True,
                "live_probed": False,
                "endpoint_url": "http://127.0.0.1:8765",
                "agentic_backend": "harness.local_agent.ServeBackend",
            },
            {
                "profile_id": "ollama-14b",
                "model": "14B",
                "backend": "ollama",
                "provider_role": "ollama_local",
                "root_exists": True,
                "supports_agentic_workflow": True,
                "live_probed": False,
                "endpoint_url": "http://127.0.0.1:11434",
                "agentic_backend": "harness.local_agent.OllamaBackend",
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_model_endpoints",
        "dry_plan": False,
        "results": [
            {
                "step_id": "model_endpoint_profiles",
                "status": "ok",
                "expected_artifacts": [str(endpoints)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["model_endpoint_signals"]
    assert signals["endpoint_artifacts"] == 1
    assert signals["profiles"] == 2
    assert signals["models_observed"] == ["14B"]
    assert signals["backends_observed"] == ["ollama", "serve"]
    assert signals["provider_roles_observed"] == ["flywheel", "ollama_local"]
    assert signals["agentic_profiles"] == 2
    markdown = render_markdown(outcome)
    assert "## Model endpoint signals" in markdown


def test_build_outcome_includes_model_endpoint_gate_signals(tmp_path):
    gate = tmp_path / "model_endpoint_gate.json"
    gate.write_text(json.dumps({
        "schema": "harness.model-endpoint-gate/v1",
        "rows": [
            {
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "health_ok": True,
                "generation_ok": True,
                "failure_class": "",
                "latency_ms": 12.5,
            }
        ],
        "summary": {"failed_rows": 0},
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_model_endpoint_gate",
        "dry_plan": False,
        "results": [
            {
                "step_id": "model_endpoint_gate",
                "status": "ok",
                "expected_artifacts": [str(gate)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["model_endpoint_signals"]
    assert signals["gate_rows"] == 1
    assert signals["gate_health_ok_rows"] == 1
    assert signals["gate_generation_ok_rows"] == 1
    assert signals["gate_failed_rows"] == 0


def test_build_outcome_includes_gather_readiness_signals(tmp_path):
    readiness = tmp_path / "gather_readiness.json"
    readiness.write_text(json.dumps({
        "schema": "harness.gather-readiness/v1",
        "summary": {
            "root_exists": True,
            "config_count": 2,
            "credential_present": False,
            "core_score": 1.0,
            "discord_score": 1.0,
            "verdict": "GATHER_STATIC_READY_NEEDS_CREDENTIAL",
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_gather",
        "dry_plan": False,
        "results": [
            {
                "step_id": "gather_readiness",
                "status": "ok",
                "expected_artifacts": [str(readiness)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["gather_readiness_signals"]
    assert signals["readiness_artifacts"] == 1
    assert signals["config_count"] == 2
    assert signals["credential_present_count"] == 0
    assert signals["verdict_counts"]["GATHER_STATIC_READY_NEEDS_CREDENTIAL"] == 1
    markdown = render_markdown(outcome)
    assert "## Gather readiness signals" in markdown


def test_build_outcome_includes_executable_manifest_signals(tmp_path):
    manifest = tmp_path / "harness_manifest.json"
    manifest.write_text(json.dumps({
        "schema": "harness.executable-manifest/v1",
        "entrypoint": "harness.cmd",
        "dispatcher": "scripts/run_harness_cli.py",
        "commands": [
            {
                "name": "manifest",
                "delegates_to": "scripts/run_harness_cli.py",
                "schemas": ["harness.executable-manifest/v1"],
                "evidence_surface": "front-controller command registry",
            },
            {
                "name": "readiness",
                "delegates_to": "metadata-only readiness/profile scripts",
                "targets": ["context", "tools"],
                "schemas": ["harness.context-inventory/v1"],
                "evidence_surface": "metadata-only readiness receipts",
            },
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_manifest",
        "dry_plan": False,
        "results": [
            {
                "step_id": "harness_executable_manifest",
                "status": "ok",
                "expected_artifacts": [str(manifest)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["executable_manifest_signals"]
    assert signals["manifest_artifacts"] == 1
    assert signals["commands"] == 2
    assert signals["command_names"] == ["manifest", "readiness"]
    assert signals["target_count"] == 2
    markdown = render_markdown(outcome)
    assert "## Executable manifest signals" in markdown


def test_build_outcome_includes_command_registry_signals(tmp_path):
    registry = tmp_path / "harness_command_registry.json"
    registry.write_text(json.dumps({
        "schema": "harness.command-registry-html/v1",
        "entrypoint": "harness.cmd",
        "html_path": "C:/tmp/harness_command_registry.html",
        "command_count": 7,
        "command_names": ["manifest", "registry", "seed"],
        "risk_counts": {"high": 1, "low": 6},
        "schema_count": 3,
        "schemas": [
            "harness.executable-manifest/v1",
            "harness.command-registry-html/v1",
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_registry",
        "dry_plan": False,
        "results": [
            {
                "step_id": "harness_command_registry",
                "status": "ok",
                "expected_artifacts": [str(registry)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["command_registry_signals"]
    assert signals["registry_artifacts"] == 1
    assert signals["commands"] == 7
    assert "registry" in signals["command_names"]
    assert signals["risk_counts"]["high"] == 1
    markdown = render_markdown(outcome)
    assert "## Command registry signals" in markdown


def test_build_outcome_includes_benchmark_profile_signals(tmp_path):
    profile = tmp_path / "benchmark_profile_manifest.json"
    profile.write_text(json.dumps({
        "schema": "harness.benchmark-profile-manifest/v1",
        "metric_weight_sum": 1.0,
        "dataset_lane_weight_sum": 1.0,
        "providers": ["serve", "codex"],
        "metrics": ["task_completion", "quality"],
        "dataset_lanes": [
            {"lane": "agentic_tool_workflows", "weight": 0.18},
            {"lane": "cross_harness_reproducibility", "weight": 0.10},
        ],
        "pressure_variables": ["tool-timeout", "adapter-skew"],
        "benchmark_suites": [
            {"suite": "seed", "benchmark_count": 3, "runnable_count": 3, "planned_count": 0},
            {"suite": "full", "benchmark_count": 2, "runnable_count": 0, "planned_count": 2},
        ],
        "benchmarks": [
            {
                "id": "m7_source_mined",
                "status": "runnable",
                "evidence_schema": "m7-source-mined-scorecard/v1",
                "coverage_units": ["buildlang_buildc_compiler_receipts"],
            },
            {"id": "local_model_release_gate_14b_32b", "status": "planned_full", "evidence_schema": "harness.model-release-readiness/v1"},
        ],
        "existing_artifacts": [{"path": "C:/tmp/m7_existing_bench_dry.json"}],
        "summary": {
            "benchmarks": 2,
            "runnable_benchmarks": 1,
            "planned_full_benchmarks": 1,
            "coverage_units": 1,
            "existing_artifacts": 1,
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_benchmarks",
        "dry_plan": False,
        "results": [
            {
                "step_id": "benchmark_profile",
                "status": "ok",
                "expected_artifacts": [str(profile)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["benchmark_profile_signals"]
    assert signals["profile_artifacts"] == 1
    assert signals["benchmarks"] == 2
    assert signals["runnable_benchmarks"] == 1
    assert signals["coverage_units"] == 1
    assert signals["existing_artifacts"] == 1
    assert signals["dataset_lanes"] == ["agentic_tool_workflows", "cross_harness_reproducibility"]
    assert signals["pressure_variables"] == ["adapter-skew", "tool-timeout"]
    assert signals["dataset_lane_weight_sums"] == [1.0]
    markdown = render_markdown(outcome)
    assert "## Benchmark profile signals" in markdown
    assert "cross_harness_reproducibility" in markdown


def test_build_outcome_includes_benchmark_execution_matrix_signals(tmp_path):
    matrix = tmp_path / "benchmark_execution_matrix.json"
    matrix.write_text(json.dumps({
        "schema": "harness.benchmark-execution-matrix/v1",
        "providers": ["serve", "codex"],
        "expected_provider_roles": ["flywheel", "codex"],
        "tiers": [
            {"tier": "dry", "step_count": 2, "long_running_steps": 0, "step_ids": ["profile_contract", "closed_loop_dry_plan"]},
            {"tier": "focused", "step_count": 3, "long_running_steps": 2, "step_ids": ["focused_closed_loop_seed", "coverage_after_execution", "outcome_synthesis"]},
            {"tier": "full", "step_count": 1, "long_running_steps": 1, "step_ids": ["full_provider_matrix"]},
        ],
        "steps": [
            {
                "step_id": "profile_contract",
                "tier": "dry",
                "expected_schemas": ["harness.benchmark-profile-manifest/v1"],
                "evidence_gates": ["metric_weight_sum"],
                "operator_approval_required": False,
                "long_running": False,
            },
            {
                "step_id": "focused_closed_loop_seed",
                "tier": "focused",
                "expected_schemas": ["harness.closed-loop-benchmark-seed/v1"],
                "evidence_gates": ["shared_run_id"],
                "operator_approval_required": True,
                "long_running": True,
            },
        ],
        "summary": {
            "steps": 6,
            "dry_steps": 2,
            "focused_steps": 3,
            "full_steps": 1,
            "long_running_steps": 3,
            "operator_approval_required_steps": 3,
            "expected_schemas": [
                "harness.benchmark-profile-manifest/v1",
                "harness.closed-loop-benchmark-seed/v1",
            ],
            "evidence_gates": ["metric_weight_sum", "shared_run_id"],
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_matrix",
        "dry_plan": False,
        "results": [
            {
                "step_id": "benchmark_execution_matrix",
                "status": "ok",
                "expected_artifacts": [str(matrix)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["benchmark_execution_matrix_signals"]
    assert signals["matrix_artifacts"] == 1
    assert signals["steps"] == 6
    assert signals["long_running_steps"] == 3
    assert signals["operator_approval_required_steps"] == 3
    assert signals["providers"] == ["codex", "serve"]
    assert signals["expected_provider_roles"] == ["codex", "flywheel"]
    assert signals["step_ids"] == ["focused_closed_loop_seed", "profile_contract"]
    assert signals["tier_step_counts"] == {"dry": 2, "focused": 3, "full": 1}
    assert "shared_run_id" in signals["evidence_gates"]
    markdown = render_markdown(outcome)
    assert "## Benchmark execution matrix signals" in markdown
    assert "focused_closed_loop_seed" in markdown


def test_build_outcome_includes_benchmark_coverage_signals(tmp_path):
    coverage = tmp_path / "benchmark_profile_coverage.json"
    coverage.write_text(json.dumps({
        "schema": "harness.benchmark-profile-coverage/v1",
        "summary": {
            "verdict": "COVERAGE_PARTIAL",
            "benchmark_coverage_rate": 0.3333,
            "unit_coverage_rate": 0.25,
            "unit_metric_completeness_rate": 0.0,
            "unit_metric_validity_rate": 0.0,
            "provider_coverage_rate": 0.5,
            "provider_unit_coverage_rate": 0.1,
            "provider_unit_validity_rate": 0.0,
            "dataset_lane_coverage_rate": 0.3333,
            "pressure_variable_coverage_rate": 0.0,
            "raw_expected_providers": ["serve", "gpt-5.3-codex-spark", "open-code"],
            "provider_aliases": {
                "serve": "flywheel",
                "gpt-5.3-codex-spark": "codex",
                "open-code": "opencode",
            },
            "missing_runnable_benchmark_ids": ["m7_governed_agent"],
            "missing_providers": ["opencode"],
            "declared_dataset_lanes": ["source_mined_codebase_tasks", "agentic_tool_workflows"],
            "observed_dataset_lanes": ["source_mined_codebase_tasks"],
            "missing_dataset_lanes": ["agentic_tool_workflows"],
            "declared_pressure_variables": ["large-context", "tool-timeout"],
            "observed_pressure_variables": [],
            "missing_pressure_variables": ["large-context", "tool-timeout"],
            "observed_benchmark_ids": ["m7_source_mined"],
            "observed_providers": ["serve", "codex"],
            "missing_units_by_benchmark": {
                "m7_source_mined": ["adversarial_pressure_weighted_benchmarks"],
            },
            "observed_units_by_benchmark": {
                "m7_source_mined": ["buildlang_buildc_compiler_receipts"],
            },
            "incomplete_units_by_benchmark": {
                "m7_source_mined": {
                    "buildlang_buildc_compiler_receipts": ["receipt"],
                }
            },
            "invalid_units_by_benchmark": {
                "m7_source_mined": {
                    "buildlang_buildc_compiler_receipts": ["receipt"],
                }
            },
            "missing_provider_units_by_benchmark": {
                "m7_source_mined": {
                    "opencode": ["buildlang_buildc_compiler_receipts"],
                }
            },
            "invalid_provider_units_by_benchmark": {
                "m7_source_mined": {
                    "codex": {
                        "buildlang_buildc_compiler_receipts": ["quality"],
                    }
                }
            },
            "load_errors": 1,
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_coverage",
        "dry_plan": False,
        "results": [
            {
                "step_id": "benchmark_profile_coverage",
                "status": "ok",
                "expected_artifacts": [str(coverage)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["benchmark_coverage_signals"]
    assert signals["coverage_artifacts"] == 1
    assert signals["missing_runnable_benchmark_ids"] == ["m7_governed_agent"]
    assert signals["missing_providers"] == ["opencode"]
    assert signals["raw_expected_providers"] == ["gpt-5.3-codex-spark", "open-code", "serve"]
    assert signals["provider_aliases"]["gpt-5.3-codex-spark"] == "codex"
    assert signals["mean_unit_coverage_rate"] == 0.25
    assert signals["mean_unit_metric_completeness_rate"] == 0.0
    assert signals["mean_unit_metric_validity_rate"] == 0.0
    assert signals["mean_provider_unit_coverage_rate"] == 0.1
    assert signals["mean_provider_unit_validity_rate"] == 0.0
    assert signals["mean_dataset_lane_coverage_rate"] == 0.3333
    assert signals["mean_pressure_variable_coverage_rate"] == 0.0
    assert signals["observed_dataset_lanes"] == ["source_mined_codebase_tasks"]
    assert signals["missing_dataset_lanes"] == ["agentic_tool_workflows"]
    assert signals["missing_pressure_variables"] == ["large-context", "tool-timeout"]
    assert signals["missing_units_by_benchmark"]["m7_source_mined"] == ["adversarial_pressure_weighted_benchmarks"]
    assert signals["incomplete_units_by_benchmark"]["m7_source_mined"]["buildlang_buildc_compiler_receipts"] == ["receipt"]
    assert signals["invalid_units_by_benchmark"]["m7_source_mined"]["buildlang_buildc_compiler_receipts"] == ["receipt"]
    assert signals["missing_provider_units_by_benchmark"]["m7_source_mined"]["opencode"] == ["buildlang_buildc_compiler_receipts"]
    assert signals["invalid_provider_units_by_benchmark"]["m7_source_mined"]["codex"]["buildlang_buildc_compiler_receipts"] == ["quality"]
    assert signals["load_errors"] == 1
    markdown = render_markdown(outcome)
    assert "## Benchmark coverage signals" in markdown
    assert "Mean dataset lane coverage rate" in markdown


def test_build_outcome_includes_agentic_task_manifest_signals_without_scorecard_count(tmp_path):
    manifest = tmp_path / "agentic_task_manifest.json"
    manifest.write_text(json.dumps({
        "schema": "harness.agentic-task-manifest/v1",
        "task_count": 1,
        "provider_roles": ["dry"],
        "task_rows": [
            {
                "task_id": "agt-010",
                "coverage_unit": "agt-010",
                "benchmark_id": "closed_loop_agentic_gauntlet",
                "dataset_lane": "agentic_tool_workflows",
                "prompt_hash": "abcdef1234567890",
            }
        ],
        "dry_scorecard_rows": [
            {
                "task_id": "agt-010",
                "coverage_unit": "agt-010",
                "provider_role": "codex",
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_agentic_manifest",
        "dry_plan": False,
        "results": [
            {
                "step_id": "agentic_task_manifest",
                "status": "ok",
                "expected_artifacts": [str(manifest)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["agentic_task_manifest_signals"]
    assert signals["manifest_artifacts"] == 1
    assert signals["task_count"] == 1
    assert signals["planned_scorecard_rows"] == 1
    assert signals["benchmark_ids"] == ["closed_loop_agentic_gauntlet"]
    assert signals["dataset_lanes"] == ["agentic_tool_workflows"]
    assert signals["coverage_units"] == ["agt-010"]
    assert signals["provider_roles"] == ["codex", "dry"]
    assert signals["prompt_hashes"] == ["abcdef1234567890"]
    assert outcome["observations"]["benchmark_signals"]["scorecard_count"] == 0
    markdown = render_markdown(outcome)
    assert "## Agentic task manifest signals" in markdown


def test_build_outcome_includes_forum_deep_verify_signals(tmp_path):
    benchmark = tmp_path / "forum_deep_verify.json"
    benchmark.write_text(json.dumps({
        "schema": "forum.deep-verify-benchmark/v1",
        "cases": [
            {
                "entry_count": 1000,
                "payload_body_bytes": 256,
                "storage_mode": "memory",
                "redaction_ratio": 0.5,
                "payloads_present": 500,
                "payloads_redacted": 500,
                "verify_chain": {"mean_ms": 0.5},
                "verify_payloads": {"mean_ms": 0.7},
                "verify_deep": {"mean_ms": 1.2},
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_forum_deep",
        "dry_plan": False,
        "results": [
            {
                "step_id": "forum_deep_verify",
                "status": "ok",
                "expected_artifacts": [str(benchmark)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["forum_deep_verify_signals"]
    assert signals["benchmark_artifacts"] == 1
    assert signals["case_count"] == 1
    assert signals["max_entry_count"] == 1000
    assert signals["max_payload_body_bytes"] == 256
    assert signals["storage_modes"] == ["memory"]
    assert signals["redaction_ratios"] == [0.5]
    assert signals["payloads_redacted"] == 500
    assert signals["mean_verify_deep_ms"] == 1.2
    assert outcome["observations"]["benchmark_signals"]["scorecard_count"] == 0
    markdown = render_markdown(outcome)
    assert "## Forum deep-verify signals" in markdown


def test_build_outcome_includes_embodied_realtime_plan_signals(tmp_path):
    plan = tmp_path / "embodied_plan.json"
    plan.write_text(json.dumps({
        "schema": "harness.embodied-realtime-multimodal/v1",
        "benchmark_id": "embodied_realtime_multimodal_pressure",
        "provider_roles": ["dry_fixture"],
        "latency_budgets_ms": [250],
        "dataset_lanes": ["embodied_realtime_multimodal"],
        "pressure_variables": ["real-time-latency"],
        "model_leads_unverified": ["Qwythos-9B-Claude-Mythos-5-1M"],
        "probe_rows": [
            {
                "probe_id": "tiny_robotics_latency",
                "provider_role": "dry_fixture",
                "latency_budget_ms": 250,
                "coverage_unit": "tiny_model_robotics_latency:dry_fixture:250ms",
                "measurements": ["first_token_ms", "task_success"],
            }
        ],
        "dry_scorecard_rows": [
            {
                "coverage_unit": "tiny_model_robotics_latency:dry_fixture:250ms",
                "provider_role": "dry_fixture",
                "failure_class": "not_executed",
            }
        ],
        "summary": {
            "probes": 1,
            "planned_probe_rows": 1,
            "planned_scorecard_rows": 1,
            "execution_status": "not_executed",
        },
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_embodied",
        "dry_plan": False,
        "results": [
            {
                "step_id": "embodied_realtime",
                "status": "ok",
                "expected_artifacts": [str(plan)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["embodied_realtime_signals"]
    assert signals["plan_artifacts"] == 1
    assert signals["planned_probe_rows"] == 1
    assert signals["planned_scorecard_rows"] == 1
    assert signals["provider_roles"] == ["dry_fixture"]
    assert signals["latency_budgets_ms"] == [250]
    assert signals["probe_ids"] == ["tiny_robotics_latency"]
    assert signals["model_leads_unverified"] == ["Qwythos-9B-Claude-Mythos-5-1M"]
    assert outcome["observations"]["benchmark_signals"]["scorecard_count"] == 0
    markdown = render_markdown(outcome)
    assert "## Embodied realtime multimodal signals" in markdown


def test_build_outcome_includes_model_card_claim_signals(tmp_path):
    claims = tmp_path / "model_card_claim_table.json"
    claims.write_text(json.dumps({
        "schema": "harness.model-card-claim-table/v1",
        "summary": {
            "model_candidates": 1,
            "claim_fields": 2,
            "verified_primary_source_fields": 0,
            "verified_secondary_source_fields": 0,
            "operator_relayed_unverified_fields": 0,
            "not_checked_fields": 2,
            "unresolved_fields": 2,
            "network_fetch": False,
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
        },
        "model_rows": [
            {
                "model_id": "Qwythos-9B-Claude-Mythos-5-1M",
                "overall_claim_status": "operator_relayed_unverified",
                "claim_fields": [
                    {"field": "model_identity", "status": "not_checked"},
                    {"field": "license", "status": "not_checked"},
                ],
            }
        ],
        "unresolved_fields": [
            {"model_id": "Qwythos-9B-Claude-Mythos-5-1M", "field": "model_identity", "status": "not_checked"},
            {"model_id": "Qwythos-9B-Claude-Mythos-5-1M", "field": "license", "status": "not_checked"},
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_claims",
        "dry_plan": False,
        "results": [
            {
                "step_id": "model_card_claim_table",
                "status": "ok",
                "expected_artifacts": [str(claims)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["model_card_claim_signals"]
    assert signals["claim_table_artifacts"] == 1
    assert signals["model_candidates"] == 1
    assert signals["claim_fields"] == 2
    assert signals["unresolved_fields"] == 2
    assert signals["not_checked_fields"] == 2
    assert signals["network_fetch_observed"] is False
    assert signals["models_observed"] == ["Qwythos-9B-Claude-Mythos-5-1M"]
    assert signals["unresolved_field_names"] == ["license", "model_identity"]
    markdown = render_markdown(outcome)
    assert "## Model-card claim signals" in markdown


def test_build_outcome_includes_harness_comparison_report_signals(tmp_path):
    comparison = tmp_path / "harness_comparison_report.json"
    comparison.write_text(json.dumps({
        "schema": "harness.comparison-report/v1",
        "conclusion": {
            "verdict": "FLYWHEEL_BETTER_ON_OBSERVED_SLICE",
            "claim": "Flywheel wins this slice.",
        },
        "summary": {
            "available_codex_flywheel_comparisons": 1,
            "flywheel_quality_wins": 1,
            "codex_quality_wins": 0,
            "quality_ties": 0,
        },
        "comparisons": [
            {
                "benchmark_id": "m7_source_mined",
                "comparison_key": "m7_source_mined",
                "available": True,
                "pass_rate_delta_flywheel_minus_codex": 0.5,
                "quality_delta_flywheel_minus_codex": 0.4,
                "latency_delta_ms_flywheel_minus_codex": -10,
                "winner_by_quality": "flywheel",
            }
        ],
    }), encoding="utf-8")
    report = {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_comparison",
        "dry_plan": False,
        "results": [
            {
                "step_id": "harness_comparison_report",
                "status": "ok",
                "expected_artifacts": [str(comparison)],
            }
        ],
        "summary": {"failed_steps": 0, "timeout_steps": 0},
    }

    outcome = build_outcome(report, source_report_path="seed.json")

    signals = outcome["observations"]["comparison_report_signals"]
    assert signals["comparison_artifacts"] == 1
    assert signals["available_comparisons"] == 1
    assert signals["flywheel_quality_wins"] == 1
    assert signals["verdict_counts"]["FLYWHEEL_BETTER_ON_OBSERVED_SLICE"] == 1
    markdown = render_markdown(outcome)
    assert "## Harness comparison signals" in markdown


def test_find_seed_report_in_store_uses_artifact_index(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "run_id": "run_123",
    }), encoding="utf-8")
    store = FileBackedHarnessStore(tmp_path / "store")
    store.copy_artifact(seed, run_id="run_123", label="closed-loop-seed-report-json")

    found = find_seed_report_in_store(store_root=str(tmp_path / "store"), run_id="run_123")

    assert found.endswith(".json")
    assert "artifacts" in found
