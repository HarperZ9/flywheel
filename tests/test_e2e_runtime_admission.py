import json
from pathlib import Path

from harness.e2e_journey_manifest import MANIFEST_SCHEMA, load_journey_manifest
from harness.e2e_runtime_admission import preflight_runtime


def _manifest(tmp_path, *, expected_executable_sha256=""):
    source = tmp_path / "source"
    fixtures = source / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.txt").write_text("E2E_SENTINEL_ALPHA\n\nE2E_SENTINEL_BETA\n", encoding="utf-8")
    path = source / "journey.json"
    path.write_text(json.dumps({
        "schema": MANIFEST_SCHEMA,
        "journey_id": "gather-context-selection-cli-private-temp-v1",
        "product": "gather",
        "product_version": "1.7.0",
        "runtime": {
            "kind": "cli_process",
            "executable_env": "GATHER_EXE",
            "expected_distribution": "gather-engine",
            "expected_version_prefix": "1.7.",
            "expected_wheel_sha256": "wheel-sha",
            "expected_executable_sha256": expected_executable_sha256,
            "forbid_pythonpath": True,
            "forbid_editable": True,
        },
        "allowed_resource_paths": ["fixtures"],
        "fixtures": {"source_text": "fixtures/sample.txt"},
        "oracle": {"kind": "gather_context_selection/v1", "include_text": "E2E_SENTINEL_ALPHA", "exclude_text": "E2E_SENTINEL_BETA", "start_marker": "E2E_SENTINEL_ALPHA", "end_marker": "E2E_SENTINEL_BETA"},
    }), encoding="utf-8")
    return load_journey_manifest(path, repo_root=source)


def test_runtime_ready_requires_installed_files_bound_to_pinned_wheel(monkeypatch, tmp_path):
    exe = tmp_path / "venv/Scripts/gather.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    monkeypatch.setenv("GATHER_EXE", str(exe))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    class Version:
        returncode = 0
        stdout = "gather 1.7.0\n"
        stderr = ""
    monkeypatch.setattr("harness.e2e_runtime_admission.subprocess.run", lambda *_args, **_kwargs: Version())
    monkeypatch.setattr("harness.e2e_runtime_admission._query_distribution_metadata", lambda *_args: (0, {
        "name": "gather-engine", "version": "1.7.0", "direct_url": {"archive_info": {"hashes": {"sha256": "wheel-sha"}}},
        "editable": False, "package_location": str(tmp_path / "venv/Lib/site-packages/gather"),
    }, ""))

    result = preflight_runtime(_manifest(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "installed_file_manifest_missing"


def test_expected_executable_hash_detects_altered_installed_launcher(monkeypatch, tmp_path):
    exe = tmp_path / "venv/Scripts/gather.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"altered-exe")
    monkeypatch.setenv("GATHER_EXE", str(exe))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    class Version:
        returncode = 0
        stdout = "gather 1.7.0\n"
        stderr = ""
    monkeypatch.setattr("harness.e2e_runtime_admission.subprocess.run", lambda *_args, **_kwargs: Version())
    monkeypatch.setattr("harness.e2e_runtime_admission._query_distribution_metadata", lambda *_args: (0, {
        "name": "gather-engine", "version": "1.7.0",
        "direct_url": {"archive_info": {"hashes": {"sha256": "wheel-sha"}}},
        "editable": False, "package_location": str(tmp_path / "venv/Lib/site-packages/gather"),
        "installed_files_sha256": "installed", "wheel_file_count": 12,
    }, ""))

    result = preflight_runtime(_manifest(tmp_path, expected_executable_sha256="0" * 64))

    assert result["status"] == "blocked"
    assert result["reason"] == "runtime_executable_hash_mismatch"
    assert result["executable_sha256"] != "0" * 64
