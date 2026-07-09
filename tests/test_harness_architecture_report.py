import json

from scripts.run_harness_architecture_report import build_report, render_markdown


def test_architecture_report_stitches_generated_contracts(tmp_path):
    release = tmp_path / "release.json"
    executable = tmp_path / "manifest.json"
    endpoints = tmp_path / "endpoints.json"
    release_readiness = tmp_path / "model_release.json"
    publish_plan = tmp_path / "model_publish.json"
    huggingface_stage = tmp_path / "huggingface.json"
    context = tmp_path / "context.json"
    pubscan = tmp_path / "pubscan.json"
    tools = tmp_path / "tools.json"
    tool_readiness = tmp_path / "tool_readiness.json"
    tool_hardening = tmp_path / "tool_hardening.json"
    tool_operator_guide = tmp_path / "tool_operator_guide.json"
    records = tmp_path / "records"
    reports = tmp_path / "reports"
    releases = tmp_path / "releases"
    flagship = tmp_path / "flagship"
    runtime = tmp_path / "runtime.json"
    codex = tmp_path / "codex.json"
    enterprise = tmp_path / "enterprise.json"
    doctor = tmp_path / "doctor.json"
    release.write_text(json.dumps({
        "schema": "harness.local-executable-release/v1",
        "executables": [{"name": "local-harness", "exists": True}],
        "skipped": ["local-serve"],
    }), encoding="utf-8")
    executable.write_text(json.dumps({
        "schema": "harness.executable-manifest/v1",
        "commands": [{"name": "manifest"}, {"name": "package-doctor"}],
    }), encoding="utf-8")
    endpoints.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {"model": "14B", "backend": "serve", "supports_agentic_workflow": True},
            {"model": "32B", "backend": "ollama", "supports_agentic_workflow": True},
        ],
    }), encoding="utf-8")
    release_readiness.write_text(json.dumps({
        "schema": "harness.model-release-readiness/v1",
        "summary": {"release_ready_models": 0, "models_with_weights": 2},
    }), encoding="utf-8")
    publish_plan.write_text(json.dumps({
        "schema": "harness.model-publish-plan/v1",
        "summary": {"status": "DO_NOT_PUBLISH"},
        "models": [{"candidate_name": "Flywheel-Local-Coder-14B"}],
    }), encoding="utf-8")
    huggingface_stage.write_text(json.dumps({
        "schema": "harness.huggingface-release-stage/v1",
        "upload_mode": "dry_run_metadata_only",
        "namespace": "HarperZ9",
        "summary": {
            "models": 2,
            "ready_to_upload_models": 0,
            "waiting_for_operator_upload_approval": 0,
            "do_not_upload_models": 2,
            "repo_ids": ["HarperZ9/flywheel-local-coder-14b"],
        },
    }), encoding="utf-8")
    context.write_text(json.dumps({
        "schema": "harness.context-inventory/v1",
        "roots_requested": ["C:/tmp"],
        "roots": [{"root": "C:/tmp", "exists": True, "truncated": False}],
        "summary": {"roots": 1, "existing_roots": 1, "entries": 2, "sensitive_name_entries": 0},
    }), encoding="utf-8")
    pubscan.write_text(json.dumps({
        "schema": "harness.pubscan-resource-profiles/v1",
        "zero_dependency_policy": {"mandatory_external_services": 0},
        "pubscan": {
            "root": "C:/dev/public/pubscan",
            "exists": True,
            "count": 13,
            "summary": {
                "profiled_entrypoints": 4,
                "source_only": 8,
                "unverified": 1,
                "native_rendering_candidates": 3,
            },
        },
        "native_rendering": {"summary": {"candidate_matches": 5}},
        "compute": {"local_cpu": {"logical_cores": 16}, "local_gpu": {"status": "unknown"}},
        "storage": {"summary": {"available_roots": 2}},
    }), encoding="utf-8")
    tools.write_text(json.dumps({
        "schema": "harness.tool-integration-contract/v1",
        "summary": {"roots_missing": 0, "enterprise_ready_static": 1},
        "tools": [{"tool": "index", "readiness": {"verdict": "PROTOTYPE_WITH_GAPS"}}],
    }), encoding="utf-8")
    tool_readiness.write_text(json.dumps({
        "schema": "harness.tool-readiness/v1",
        "summary": {"tools": 3, "existing_tools": 3, "enterprise_ready_tools": 1, "prototype_with_gaps": 2, "mean_score": 0.8},
        "tools": [
            {"tool": "mneme", "verdict": "ENTERPRISE_READY_STATIC", "score": 1.0, "enterprise_ready": True},
            {"tool": "relay", "verdict": "PROTOTYPE_WITH_GAPS", "score": 0.7, "enterprise_ready": False},
        ],
    }), encoding="utf-8")
    tool_hardening.write_text(json.dumps({
        "schema": "harness.tool-hardening-plan/v1",
        "summary": {
            "tools": 3,
            "actions": 2,
            "p0_actions": 0,
            "p1_actions": 1,
            "release_gates": 9,
            "passed_release_gates": 7,
            "source_loaded": True,
            "enterprise_ready_static": False,
        },
    }), encoding="utf-8")
    tool_operator_guide.write_text(json.dumps({
        "schema": "harness.tool-operator-guide/v1",
        "summary": {"tools": 2, "roots_existing": 2, "enterprise_ready": 1},
        "tools": [{"tool": "index"}, {"tool": "mneme"}],
    }), encoding="utf-8")
    records.mkdir()
    for name in [
        "ROADMAP-STATUS-2026-07-09.md",
        "CAPABILITY-CATALOG-2026-07-09.md",
        "OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md",
        "OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.json",
        "NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-07-09.md",
    ]:
        (records / name).write_text("record\n", encoding="utf-8")
    reports.mkdir()
    (records / "BENCHMARK-METHODOLOGY-2026-07-09.md").write_text("methodology\n", encoding="utf-8")
    for name in [
        "EXPERIMENTAL-OUTCOME-CODEX-FLYWHEEL-LOCAL-ENGINE-2026-07-09.md",
        "PUBSCAN-ZERO-DEPENDENCY-INTEGRATION-2026-07-09.md",
        "PUBLIC-REDTEAM-CONTEXT-BOUNDARY-2026-07-09.md",
    ]:
        (reports / name).write_text("report\n", encoding="utf-8")
    for model in ["14B", "32B"]:
        (releases / model).mkdir(parents=True)
        for name in ["README.md", "MODEL_CARD.md", "BENCHMARKS.md", "ENDPOINTS.md", "USAGE.md", "SAFETY-ACCOUNTABILITY.md", "RELEASE-CHECKLIST.md"]:
            (releases / model / name).write_text("release\n", encoding="utf-8")
    flagship.mkdir()
    for name in ["README.md", "DEMOS.md", "WALKTHROUGH.md", "EXTERNAL-DOCS-SYNC.md", "EXTERNAL-CONTEXT-SOURCES.md"]:
        (flagship / name).write_text("flagship\n", encoding="utf-8")
    (flagship / "assets").mkdir()
    (flagship / "assets" / "flywheel-flagship-mark.svg").write_text("<svg />\n", encoding="utf-8")
    runtime.write_text(json.dumps({
        "schema": "harness.runtime-activation-contract/v1",
        "summary": {"ready_for_package_inspection": True},
        "activation_steps": ["inspect manifest"],
    }), encoding="utf-8")
    codex.write_text(json.dumps({
        "schema": "harness.codex-mcp-launch-contract/v1",
        "summary": {"servers_ready": 1},
        "servers": [],
        "session_reload_boundary": {"code_or_config_fix_requires_host_reload": True},
    }), encoding="utf-8")
    enterprise.write_text(json.dumps({
        "schema": "harness.enterprise-readiness-report/v1",
        "summary": {"verdict": "HARDENING_REQUIRED"},
        "tools": [{"tool": "mneme"}],
    }), encoding="utf-8")
    doctor.write_text(json.dumps({
        "schema": "harness.package-ship-doctor/v1",
        "summary": {"verdict": "SHIP_READY", "hard_failures": 0},
    }), encoding="utf-8")

    report = build_report(
        release_manifest_path=release,
        executable_manifest_path=executable,
        context_inventory_path=context,
        pubscan_profiles_path=pubscan,
        endpoint_profiles_path=endpoints,
        model_release_path=release_readiness,
        model_publish_path=publish_plan,
        huggingface_stage_path=huggingface_stage,
        tool_contract_path=tools,
        tool_readiness_path=tool_readiness,
        tool_hardening_path=tool_hardening,
        tool_operator_guide_path=tool_operator_guide,
        documentation_records_root=records,
        documentation_reports_root=reports,
        model_release_docs_root=releases,
        flagship_docs_root=flagship,
        runtime_contract_path=runtime,
        codex_mcp_contract_path=codex,
        enterprise_readiness_path=enterprise,
        package_doctor_path=doctor,
    )

    assert report["schema"] == "harness.architecture-report/v1"
    assert report["summary"]["models"] == ["14B", "32B"]
    assert report["summary"]["model_candidate_names"] == ["Flywheel-Local-Coder-14B"]
    assert report["summary"]["context_entries"] == 2
    assert report["summary"]["pubscan_repositories"] == 13
    assert report["summary"]["pubscan_profiled_entrypoints"] == 4
    assert report["summary"]["tool_readiness_enterprise_ready"] == 1
    assert report["summary"]["tool_hardening_actions"] == 2
    assert report["summary"]["tool_operator_guided_tools"] == 2
    assert report["summary"]["documentation_records_present"] == 5
    assert report["summary"]["documentation_reports_present"] == 4
    assert report["summary"]["model_release_documents_present"] == 14
    assert report["summary"]["flagship_documents_present"] == 6
    assert report["summary"]["huggingface_do_not_upload"] == 2
    assert report["summary"]["tools"] == ["index"]
    assert report["release_gate"]["package_doctor_verdict"] == "SHIP_READY"


def test_architecture_report_markdown_includes_next_gates(tmp_path):
    missing = tmp_path / "missing.json"
    report = build_report(
        release_manifest_path=missing,
        executable_manifest_path=missing,
        context_inventory_path=missing,
        pubscan_profiles_path=missing,
        endpoint_profiles_path=missing,
        model_release_path=missing,
        model_publish_path=missing,
        huggingface_stage_path=missing,
        tool_contract_path=missing,
        tool_readiness_path=missing,
        tool_hardening_path=missing,
        tool_operator_guide_path=missing,
        documentation_records_root=tmp_path / "missing-records",
        documentation_reports_root=tmp_path / "missing-reports",
        model_release_docs_root=tmp_path / "missing-releases",
        flagship_docs_root=tmp_path / "missing-flagship",
        runtime_contract_path=missing,
        codex_mcp_contract_path=missing,
        enterprise_readiness_path=missing,
        package_doctor_path=missing,
    )
    markdown = render_markdown(report)

    assert "# Harness architecture and endpoint report" in markdown
    assert "Next gates" in markdown
