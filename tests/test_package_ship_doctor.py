import hashlib
import json
import zipfile

from scripts.run_package_ship_doctor import REQUIRED_BUNDLE_FILES, build_doctor, render_markdown


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_package_ship_doctor_accepts_complete_metadata_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    source_commit = "a" * 40
    files = []
    payloads = {
        "config/model_endpoint_profiles.local.json": {
            "schema": "harness.model-endpoint-profiles/v1",
            "profiles": [
                {"model": "14B", "backend": "serve"},
                {"model": "14B", "backend": "ollama"},
                {"model": "32B", "backend": "serve"},
                {"model": "32B", "backend": "ollama"},
            ],
        },
        "config/model_release_readiness.local.json": {
            "schema": "harness.model-release-readiness/v1",
            "summary": {"release_ready_models": 0},
        },
        "config/model_publish_plan.local.json": {
            "schema": "harness.model-publish-plan/v1",
            "summary": {"status": "DO_NOT_PUBLISH"},
        },
        "config/tool_integration_contract.local.json": {
            "schema": "harness.tool-integration-contract/v1",
        },
        "config/tool_readiness.local.json": {
            "schema": "harness.tool-readiness/v1",
            "summary": {"enterprise_ready_tools": 1, "tools": 3},
        },
        "config/tool_hardening_plan.local.json": {
            "schema": "harness.tool-hardening-plan/v1",
            "summary": {"actions": 2, "source_loaded": True},
        },
        "config/runtime_activation_contract.local.json": {
            "schema": "harness.runtime-activation-contract/v1",
        },
        "config/codex_mcp_launch_contract.local.json": {
            "schema": "harness.codex-mcp-launch-contract/v1",
        },
        "config/context_inventory.local.json": {
            "schema": "harness.context-inventory/v1",
            "summary": {"entries": 3, "existing_roots": 1, "roots": 1},
        },
        "config/pubscan_resource_profiles.local.json": {
            "schema": "harness.pubscan-resource-profiles/v1",
            "pubscan": {"summary": {"profiled_entrypoints": 1}, "count": 1},
        },
        "config/harness_architecture_report.local.json": {
            "schema": "harness.architecture-report/v1",
        },
        "config/enterprise_readiness_report.local.json": {
            "schema": "harness.enterprise-readiness-report/v1",
        },
        "manifest/harness_executable_manifest.local.json": {
            "schema": "harness.executable-manifest/v1",
        },
    }
    for rel in REQUIRED_BUNDLE_FILES:
        path = bundle / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel in payloads:
            path.write_text(json.dumps(payloads[rel]), encoding="utf-8")
        else:
            path.write_text("release file\n", encoding="utf-8")
        files.append({
            "path": str(path),
            "relative_path": rel,
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        })

    zip_path = tmp_path / "local-harness.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for row in files:
            zf.write(row["path"], row["relative_path"])

    repo = tmp_path / "repo"
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / ".git" / "refs" / "heads" / "main").write_text(source_commit, encoding="utf-8")
    summary = {
        "schema": "harness.local-release-bundle/v1",
        "package_name": "local-harness-test",
        "source_commit": source_commit,
        "files": files,
        "included_integrity_files": [],
        "zip": {
            "path": str(zip_path),
            "bytes": zip_path.stat().st_size,
            "sha256": _sha(zip_path),
        },
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    doctor = build_doctor(package_summary=summary_path, repo_root=repo)

    assert doctor["schema"] == "harness.package-ship-doctor/v1"
    assert doctor["summary"]["verdict"] == "SHIP_READY"
    assert doctor["summary"]["hard_failures"] == 0


def test_package_ship_doctor_markdown_names_verdict(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps({
            "package_name": "broken",
            "source_commit": "",
            "files": [],
            "included_integrity_files": [],
            "zip": {"path": str(tmp_path / "missing.zip"), "sha256": ""},
        }),
        encoding="utf-8",
    )

    doctor = build_doctor(package_summary=summary_path, repo_root=tmp_path)
    markdown = render_markdown(doctor)

    assert "# Package ship doctor" in markdown
    assert "Verdict:" in markdown
    assert "harness.package-ship-doctor/v1" in markdown
