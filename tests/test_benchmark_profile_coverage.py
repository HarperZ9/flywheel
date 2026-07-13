import json

from scripts.run_benchmark_profile_coverage import (
    build_coverage_report,
    observed_artifact_summary,
    render_markdown,
)


def profile_fixture():
    return {
        "schema": "harness.benchmark-profile-manifest/v1",
        "profile_id": "test_profile",
        "providers": ["serve", "gpt-5.3-codex-spark", "open-code"],
        "expected_provider_roles": ["flywheel", "codex", "opencode"],
        "provider_aliases": {
            "serve": "flywheel",
            "flywheel": "flywheel",
            "codex": "codex",
            "gpt-5.3-codex-spark": "codex",
            "open-code": "opencode",
            "opencode": "opencode",
        },
        "metric_weight_sum": 1.0,
        "dataset_lane_weight_sum": 1.0,
        "dataset_lanes": [
            {
                "lane": "source_mined_codebase_tasks",
                "weight": 0.4,
                "pressure_variables": ["large-context", "stale-docs"],
            },
            {
                "lane": "agentic_tool_workflows",
                "weight": 0.3,
                "pressure_variables": ["tool-timeout", "malformed-json"],
            },
            {
                "lane": "guardrail_accountability_friction",
                "weight": 0.3,
                "pressure_variables": ["unnecessary-refusal", "latency-tax"],
            },
        ],
        "pressure_variables": [
            "large-context",
            "stale-docs",
            "tool-timeout",
            "malformed-json",
            "unnecessary-refusal",
            "latency-tax",
        ],
        "benchmarks": [
            {
                "id": "m7_source_mined",
                "status": "runnable",
                "coverage_units": ["buildlang_buildc_compiler_receipts", "adversarial_pressure_weighted_benchmarks"],
            },
            {
                "id": "m7_governed_agent",
                "status": "runnable",
                "coverage_units": ["maturity_tier_promotion"],
            },
            {
                "id": "unisonai_stateful_provider_matrix",
                "status": "runnable",
                "coverage_units": ["stateful_action_json"],
            },
            {
                "id": "classifier_friction_accountability",
                "status": "runnable",
                "coverage_units": ["enterprise_vuln_triage_safe:guardrail_on"],
            },
            {"id": "local_model_release_gate_14b_32b", "status": "planned_full", "coverage_units": ["14B", "32B"]},
        ],
    }


def test_observed_artifact_summary_maps_m7_source_schema_to_benchmark_id():
    data = {
        "schema": "m7-source-mined-scorecard/v1",
        "case_results": [
            {
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 0.8,
                "latency_ms": 123,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
            },
        ],
        "backend_rows": [
            {"provider": "serve"},
            {"provider": "codex"},
        ],
    }

    summary = observed_artifact_summary(data, "m7.json")

    assert summary["benchmark_id"] == "m7_source_mined"
    assert summary["providers"] == ["codex", "serve"]
    assert summary["unit_ids"] == ["buildlang_buildc_compiler_receipts"]
    assert summary["unit_metric_completeness"]["buildlang_buildc_compiler_receipts"]["complete"] is True
    assert summary["unit_metric_completeness"]["buildlang_buildc_compiler_receipts"]["valid"] is True
    assert summary["row_count"] == 2


def test_observed_artifact_summary_reads_legacy_m7_source_rows():
    data = {
        "schema": "m7-source-mined-scorecard/v1",
        "rows": [
            {"provider": "serve", "provider_role": "flywheel"},
        ],
    }

    summary = observed_artifact_summary(data, "legacy_m7.json")

    assert summary["providers"] == ["flywheel"]
    assert summary["row_count"] == 1


def test_observed_artifact_summary_maps_model_endpoint_profiles_to_release_gate():
    data = {
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "root_exists": True,
            },
            {
                "model": "32B",
                "backend": "ollama",
                "provider_role": "ollama_local",
                "root_exists": False,
            },
        ],
    }

    summary = observed_artifact_summary(data, "model_endpoints.json")

    assert summary["benchmark_id"] == "local_model_release_gate_14b_32b"
    assert summary["providers"] == ["flywheel", "ollama_local"]
    assert summary["unit_ids"] == ["14B", "32B"]
    assert summary["row_count"] == 2


def test_observed_artifact_summary_maps_model_endpoint_gate_rows_to_release_gate():
    data = {
        "schema": "harness.model-endpoint-gate/v1",
        "rows": [
            {
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "health_ok": True,
                "generation_ok": True,
                "latency_ms": 12,
                "quality_score": 1.0,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
                "response_sha256": "abcdef1234567890",
            },
            {
                "model": "32B",
                "backend": "ollama",
                "provider_role": "ollama_local",
                "health_ok": False,
                "generation_ok": False,
                "latency_ms": 5,
                "quality_score": 0.0,
                "failure_class": "endpoint_unavailable",
                "receipt_hash": "abcdef1234567891",
                "response_sha256": "",
            },
        ],
    }

    summary = observed_artifact_summary(data, "model_endpoint_gate.json")

    assert summary["benchmark_id"] == "local_model_release_gate_14b_32b"
    assert summary["providers"] == ["flywheel", "ollama_local"]
    assert summary["unit_ids"] == ["14B", "32B"]
    assert summary["unit_metric_completeness"]["14B"]["complete"] is True
    assert summary["unit_metric_completeness"]["14B"]["valid"] is True
    assert summary["unit_metric_completeness"]["32B"]["complete"] is True
    assert summary["unit_metric_completeness"]["32B"]["valid"] is True
    assert summary["row_count"] == 2


def test_observed_artifact_summary_maps_classifier_friction_rows_to_benchmark_id():
    data = {
        "schema": "classifier-friction-benchmark/v1",
        "results": [
            {
                "coverage_unit": "enterprise_vuln_triage_safe:guardrail_on",
                "task_id": "enterprise_vuln_triage_safe",
                "provider": "codex",
                "provider_role": "codex",
                "mode": "guardrail_on",
                "quality_score": 0.8,
                "latency_ms": 25,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
            }
        ],
    }

    summary = observed_artifact_summary(data, "classifier.json")

    assert summary["benchmark_id"] == "classifier_friction_accountability"
    assert summary["providers"] == ["codex"]
    assert summary["unit_ids"] == ["enterprise_vuln_triage_safe:guardrail_on"]
    assert summary["unit_metric_completeness"]["enterprise_vuln_triage_safe:guardrail_on"]["complete"] is True
    assert summary["unit_metric_completeness"]["enterprise_vuln_triage_safe:guardrail_on"]["valid"] is True
    assert summary["dataset_lanes"] == ["guardrail_accountability_friction"]
    assert summary["row_count"] == 1


def test_observed_artifact_summary_extracts_explicit_dataset_lane_and_pressure_variables():
    data = {
        "schema": "classifier-friction-benchmark/v1",
        "dataset_lane": "guardrail_accountability_friction",
        "pressure_variables": ["unnecessary-refusal"],
        "results": [
            {
                "coverage_unit": "enterprise_vuln_triage_safe:guardrail_on",
                "provider": "codex",
                "quality_score": 0.8,
                "latency_ms": 25,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
                "pressure_variable": "latency-tax",
            }
        ],
    }

    summary = observed_artifact_summary(data, "classifier.json")

    assert summary["dataset_lanes"] == ["guardrail_accountability_friction"]
    assert summary["pressure_variables"] == ["latency-tax", "unnecessary-refusal"]


def test_observed_artifact_summary_maps_forum_deep_verify_benchmark():
    data = {
        "schema": "forum.deep-verify-benchmark/v1",
        "cases": [
            {
                "entry_count": 1000,
                "payload_body_bytes": 256,
                "storage_mode": "memory",
                "redaction_ratio": 0.5,
                "verify_deep": {"mean_ms": 1.2},
            }
        ],
    }

    summary = observed_artifact_summary(data, "forum_deep_verify.json")

    assert summary["benchmark_id"] == "forum_ledger_deep_verify_scaling"
    assert summary["dataset_lanes"] == ["adversarial_receipt_integrity", "replayable_causal_ledger_scaling"]
    assert summary["pressure_variables"] == ["entry-count-scale", "payload-byte-scale", "redaction-ratio"]
    assert summary["unit_ids"] == ["memory:1000:256:redact=0.5"]
    assert summary["row_count"] == 1


def test_observed_artifact_summary_marks_embodied_realtime_plan_as_planned_only():
    data = {
        "schema": "harness.embodied-realtime-multimodal/v1",
        "benchmark_id": "embodied_realtime_multimodal_pressure",
        "dataset_lanes": ["embodied_realtime_multimodal"],
        "pressure_variables": ["real-time-latency"],
        "summary": {"planned_probe_rows": 1},
        "dry_scorecard_rows": [
            {
                "coverage_unit": "tiny_model_robotics_latency:dry_fixture:250ms",
                "provider_role": "dry_fixture",
                "failure_class": "not_executed",
            }
        ],
    }

    summary = observed_artifact_summary(data, "embodied.json")

    assert summary["planned_only"] is True
    assert summary["benchmark_id"] == "embodied_realtime_multimodal_pressure"
    assert summary["planned_provider_roles"] == ["dry_fixture"]
    assert summary["planned_units_by_benchmark"] == {
        "embodied_realtime_multimodal_pressure": ["tiny_model_robotics_latency:dry_fixture:250ms"]
    }
    assert summary["dataset_lanes"] == ["embodied_realtime_multimodal"]
    assert summary["pressure_variables"] == ["real-time-latency"]


def test_observed_artifact_summary_marks_model_card_claim_table_as_planned_only():
    data = {
        "schema": "harness.model-card-claim-table/v1",
        "model_rows": [
            {
                "model_id": "Qwythos-9B-Claude-Mythos-5-1M",
                "claim_fields": [
                    {"field": "model_identity", "status": "not_checked"},
                    {"field": "license", "status": "not_checked"},
                ],
            }
        ],
        "summary": {
            "model_candidates": 1,
            "claim_fields": 2,
            "unresolved_fields": 2,
            "all_primary_sourced": False,
        },
    }

    summary = observed_artifact_summary(data, "model_card_claims.json")

    assert summary["planned_only"] is True
    assert summary["benchmark_id"] == "embodied_realtime_multimodal_pressure"
    assert summary["planned_units_by_benchmark"] == {
        "embodied_realtime_multimodal_pressure": ["Qwythos-9B-Claude-Mythos-5-1M"]
    }
    assert summary["dataset_lanes"] == ["embodied_realtime_multimodal", "local_resource_pressure"]
    assert summary["pressure_variables"] == ["model-card-unverified"]
    assert summary["claim_fields"] == 2
    assert summary["unresolved_fields"] == 2


def test_observed_artifact_summary_marks_cross_harness_manifest_as_planned_only():
    data = {
        "schema": "harness.cross-harness-manifest/v1",
        "task_count": 1,
        "provider_roles": ["codex_harness", "flywheel_harness"],
        "dataset_lanes": ["cross_harness_reproducibility"],
        "task_rows": [
            {
                "task_id": "agt-001",
                "coverage_unit": "agt-001",
                "benchmark_id": "cross_harness_reproducibility_matrix",
                "dataset_lane": "cross_harness_reproducibility",
            }
        ],
        "dry_scorecard_rows": [
            {
                "task_id": "agt-001",
                "coverage_unit": "agt-001",
                "benchmark_id": "cross_harness_reproducibility_matrix",
                "provider_role": "codex_harness",
                "execution_mode": "manifest_only",
            }
        ],
    }

    summary = observed_artifact_summary(data, "cross.json")

    assert summary["planned_only"] is True
    assert summary["benchmark_id"] == "cross_harness_reproducibility_matrix"
    assert summary["planned_provider_roles"] == ["codex_harness", "flywheel_harness"]
    assert summary["planned_units_by_benchmark"] == {"cross_harness_reproducibility_matrix": ["agt-001"]}
    assert summary["dataset_lanes"] == ["cross_harness_reproducibility"]


def test_observed_artifact_summary_marks_adapter_runtime_matrix_as_planned_only():
    data = {
        "schema": "harness.adapter-runtime-matrix/v1",
        "runtime_rows": [
            {"provider_role": "codex_harness", "manifest_ready": True},
            {"provider_role": "local_14b", "manifest_ready": True},
        ],
    }

    summary = observed_artifact_summary(data, "adapter_runtime_matrix.json")

    assert summary["planned_only"] is True
    assert summary["benchmark_id"] == "cross_harness_reproducibility_matrix"
    assert summary["planned_units_by_benchmark"] == {
        "cross_harness_reproducibility_matrix": ["codex_harness", "local_14b"]
    }
    assert summary["planned_provider_roles"] == ["codex_harness", "local_14b"]
    assert "endpoint_release_gates" in summary["dataset_lanes"]
    assert "endpoint-gate" in summary["pressure_variables"]


def test_coverage_report_flags_missing_runnable_benchmarks_and_providers(tmp_path):
    m7 = tmp_path / "m7.json"
    m7.write_text(json.dumps({
        "schema": "m7-source-mined-scorecard/v1",
        "case_results": [
            {
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 0.8,
                "latency_ms": 123,
                "failure_class": "",
            }
        ],
        "backend_rows": [{"provider": "serve"}, {"provider": "codex"}, {"provider": "opencode", "skipped": True}],
    }), encoding="utf-8")

    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[str(m7)],
    )

    summary = report["summary"]
    assert summary["verdict"] == "COVERAGE_PARTIAL"
    assert summary["observed_benchmark_ids"] == ["m7_source_mined"]
    assert summary["missing_runnable_benchmark_ids"] == [
        "m7_governed_agent",
        "unisonai_stateful_provider_matrix",
        "classifier_friction_accountability",
    ]
    assert summary["missing_providers"] == ["opencode"]
    assert summary["raw_expected_providers"] == ["serve", "gpt-5.3-codex-spark", "open-code"]
    assert summary["observed_providers"] == ["codex", "flywheel"]
    assert summary["benchmark_coverage_rate"] == 0.25
    assert summary["unit_coverage_rate"] == 0.2
    assert summary["missing_units_by_benchmark"]["classifier_friction_accountability"] == ["enterprise_vuln_triage_safe:guardrail_on"]
    assert summary["missing_units_by_benchmark"]["m7_source_mined"] == ["adversarial_pressure_weighted_benchmarks"]
    assert summary["missing_units_by_benchmark"]["m7_governed_agent"] == ["maturity_tier_promotion"]
    assert summary["unit_metric_completeness_rate"] == 0.0
    assert summary["incomplete_units_by_benchmark"]["m7_source_mined"]["buildlang_buildc_compiler_receipts"] == ["receipt"]
    assert summary["observed_dataset_lanes"] == ["source_mined_codebase_tasks"]
    assert summary["missing_dataset_lanes"] == [
        "agentic_tool_workflows",
        "guardrail_accountability_friction",
    ]
    assert summary["dataset_lane_coverage_rate"] == 0.3333
    assert summary["missing_pressure_variables"] == [
        "large-context",
        "latency-tax",
        "malformed-json",
        "stale-docs",
        "tool-timeout",
        "unnecessary-refusal",
    ]
    assert summary["pressure_variable_coverage_rate"] == 0.0


def test_agentic_task_manifest_is_planned_only_coverage(tmp_path):
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

    artifact = observed_artifact_summary(json.loads(manifest.read_text(encoding="utf-8")), str(manifest))
    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[str(manifest)],
    )

    assert artifact["planned_only"] is True
    assert artifact["planned_units_by_benchmark"] == {"closed_loop_agentic_gauntlet": ["agt-010"]}
    assert artifact["planned_provider_roles"] == ["codex", "dry"]
    assert artifact["row_count"] == 1
    summary = report["summary"]
    assert summary["planned_benchmark_ids"] == ["closed_loop_agentic_gauntlet"]
    assert summary["planned_units_by_benchmark"] == {"closed_loop_agentic_gauntlet": ["agt-010"]}
    assert summary["planned_provider_roles"] == ["codex", "dry"]
    assert summary["planned_dataset_lanes"] == ["agentic_tool_workflows"]
    assert summary["observed_benchmark_ids"] == []
    assert "closed_loop_agentic_gauntlet" not in summary["observed_benchmark_ids"]
    assert summary["verdict"] == "COVERAGE_PARTIAL"


def test_coverage_report_counts_unreadable_artifacts(tmp_path):
    missing = tmp_path / "missing.json"

    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[str(missing)],
    )

    assert report["summary"]["load_errors"] == 1
    assert report["load_errors"][0]["error"] == "missing_artifact"


def test_render_markdown_surfaces_missing_coverage(tmp_path):
    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[],
    )

    markdown = render_markdown(report)

    assert "# Benchmark profile coverage" in markdown
    assert "COVERAGE_PARTIAL" in markdown
    assert "m7_source_mined" in markdown
    assert "Unit coverage rate" in markdown
    assert "Unit metric completeness rate" in markdown
    assert "Dataset lane coverage rate" in markdown
    assert "Pressure variable coverage rate" in markdown
    assert "opencode" in markdown


def test_coverage_report_flags_invalid_metric_shapes(tmp_path):
    m7 = tmp_path / "m7_invalid_metrics.json"
    m7.write_text(json.dumps({
        "schema": "m7-source-mined-scorecard/v1",
        "case_results": [
            {
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 2.0,
                "latency_ms": -5,
                "failure_class": "maybe_bad",
                "receipt_hash": "abc",
            }
        ],
        "backend_rows": [{"provider": "serve"}, {"provider": "codex"}],
    }), encoding="utf-8")

    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[str(m7)],
    )

    invalid = report["summary"]["invalid_units_by_benchmark"]["m7_source_mined"]["buildlang_buildc_compiler_receipts"]
    assert invalid == ["failure_class", "latency", "quality", "receipt"]
    assert report["summary"]["unit_metric_validity_rate"] == 0.0


def test_coverage_report_tracks_provider_by_unit_evidence(tmp_path):
    m7 = tmp_path / "m7_provider_units.json"
    m7.write_text(json.dumps({
        "schema": "m7-source-mined-scorecard/v1",
        "case_results": [
            {
                "provider": "serve",
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 0.8,
                "latency_ms": 10,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
            },
            {
                "provider": "codex",
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 2.0,
                "latency_ms": 10,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
            },
            {
                "provider": "opencode",
                "skipped": True,
                "case_id": "buildlang_buildc_compiler_receipts",
                "quality": 0.8,
                "latency_ms": 10,
                "failure_class": "",
                "receipt_hash": "abcdef1234567890",
            },
        ],
        "backend_rows": [{"provider": "serve"}, {"provider": "codex"}, {"provider": "opencode", "skipped": True}],
    }), encoding="utf-8")

    report = build_coverage_report(
        profile_fixture(),
        profile_path="profile.json",
        artifact_paths=[str(m7)],
    )

    summary = report["summary"]
    assert summary["observed_provider_units_by_benchmark"]["m7_source_mined"]["flywheel"] == ["buildlang_buildc_compiler_receipts"]
    assert summary["missing_provider_units_by_benchmark"]["m7_source_mined"]["opencode"] == [
        "adversarial_pressure_weighted_benchmarks",
        "buildlang_buildc_compiler_receipts",
    ]
    assert summary["invalid_provider_units_by_benchmark"]["m7_source_mined"]["codex"]["buildlang_buildc_compiler_receipts"] == ["quality"]
    assert summary["provider_unit_coverage_rate"] == 0.1333
    assert summary["provider_unit_validity_rate"] == 0.0667
