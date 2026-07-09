import json

from scripts.run_harness_architecture_report import build_report, render_markdown


def test_architecture_report_stitches_generated_contracts(tmp_path):
    release = tmp_path / "release.json"
    executable = tmp_path / "manifest.json"
    endpoints = tmp_path / "endpoints.json"
    tools = tmp_path / "tools.json"
    runtime = tmp_path / "runtime.json"
    codex = tmp_path / "codex.json"
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
    tools.write_text(json.dumps({
        "schema": "harness.tool-integration-contract/v1",
        "summary": {"roots_missing": 0, "enterprise_ready_static": 1},
        "tools": [{"tool": "index", "readiness": {"verdict": "PROTOTYPE_WITH_GAPS"}}],
    }), encoding="utf-8")
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
    doctor.write_text(json.dumps({
        "schema": "harness.package-ship-doctor/v1",
        "summary": {"verdict": "SHIP_READY", "hard_failures": 0},
    }), encoding="utf-8")

    report = build_report(
        release_manifest_path=release,
        executable_manifest_path=executable,
        endpoint_profiles_path=endpoints,
        tool_contract_path=tools,
        runtime_contract_path=runtime,
        codex_mcp_contract_path=codex,
        package_doctor_path=doctor,
    )

    assert report["schema"] == "harness.architecture-report/v1"
    assert report["summary"]["models"] == ["14B", "32B"]
    assert report["summary"]["tools"] == ["index"]
    assert report["release_gate"]["package_doctor_verdict"] == "SHIP_READY"


def test_architecture_report_markdown_includes_next_gates(tmp_path):
    missing = tmp_path / "missing.json"
    report = build_report(
        release_manifest_path=missing,
        executable_manifest_path=missing,
        endpoint_profiles_path=missing,
        tool_contract_path=missing,
        runtime_contract_path=missing,
        codex_mcp_contract_path=missing,
        package_doctor_path=missing,
    )
    markdown = render_markdown(report)

    assert "# Harness architecture and endpoint report" in markdown
    assert "Next gates" in markdown
