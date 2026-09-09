import json
import os
import hashlib
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from harness.e2e_journey_manifest import load_journey_manifest
from harness.e2e_runner import run_journey
from harness.e2e_runtime_admission import preflight_runtime

FIXTURE_DIR = Path("tests/fixtures/e2e/gather_context")


def _assert_gather_result(result):
    assert result.status == "completed"
    assert result.primary_outcome == "semantic_pass"
    assert result.oracle["status"] == "pass"
    assert result.semantic_status == "pass"
    assert result.calibration["wrong_body"]["status"] == "pass"
    assert result.calibration["wrong_body"]["oracle_status"] == "fail"
    assert result.calibration["tamper_refusal"]["status"] == "pass"
    assert result.runtime["version"] == "1.7.0"
    assert result.runtime["editable"] is False
    assert result.runtime["direct_url"]["archive_info"]["hashes"]["sha256"] == "69fdea1aee67c6dd8a0d93c40bcb51476edb26c0163e6e7e25f4c86c1bb7b0c6"
    payload = json.loads(Path(result.artifacts["run_result"]).read_text(encoding="utf-8"))
    assert payload["schema"] == "flywheel.product-e2e-run/v1"
    assert Path(result.workspace_root).is_dir()


def _wheel_from_current_runtime(tmp_path) -> Path | None:
    if not os.environ.get("FLYWHEEL_E2E_GATHER17_EXE"):
        result = run_journey(FIXTURE_DIR / "gather-cli-context.json", artifact_root=tmp_path / "missing", run_id="missing-for-clone")
        assert result.status == "blocked"
        return None
    manifest = load_journey_manifest(FIXTURE_DIR / "gather-cli-context.json")
    runtime = preflight_runtime(manifest)
    assert runtime["status"] == "ready"
    parsed = urlparse(runtime["direct_url"]["url"])
    assert parsed.scheme == "file"
    return Path(unquote(parsed.path.lstrip("/")) if os.name == "nt" else unquote(parsed.path))


def _install_clone(tmp_path, wheel: Path) -> Path:
    clone = tmp_path / "venv-clone"
    subprocess.run([sys.executable, "-m", "venv", str(clone)], check=True, text=True, capture_output=True)
    python = clone / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", str(wheel)],
                   check=True, text=True, capture_output=True)
    return clone / ("Scripts/gather.exe" if os.name == "nt" else "bin/gather")


def _manifest_with_expected_exe(tmp_path, exe_sha256: str) -> Path:
    source = tmp_path / "source"
    fixture_dir = source / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "sample.txt").write_text((FIXTURE_DIR / "sample.txt").read_text(encoding="utf-8"), encoding="utf-8")
    data = json.loads((FIXTURE_DIR / "gather-cli-context.json").read_text(encoding="utf-8"))
    data["allowed_resource_paths"] = ["fixtures"]
    data["fixtures"] = {"source_text": "fixtures/sample.txt"}
    data["runtime"]["expected_executable_sha256"] = exe_sha256
    path = source / "manifest.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_missing_gather17_runtime_is_blocked_not_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("FLYWHEEL_E2E_GATHER17_EXE", raising=False)

    result = run_journey(FIXTURE_DIR / "gather-cli-context.json", artifact_root=tmp_path / "artifacts", run_id="missing-runtime")

    assert result.status == "blocked"
    assert result.primary_outcome == "runtime_unavailable"
    assert result.oracle["status"] == "not_run"


def test_installed_gather17_cli_context_journey(tmp_path):
    result = run_journey(FIXTURE_DIR / "gather-cli-context.json", artifact_root=tmp_path / "artifacts", run_id="gather-cli-real")
    if not os.environ.get("FLYWHEEL_E2E_GATHER17_EXE"):
        assert result.status == "blocked"
        assert result.primary_outcome == "runtime_unavailable"
        return
    _assert_gather_result(result)


def test_installed_gather17_mcp_context_journey(tmp_path):
    result = run_journey(FIXTURE_DIR / "gather-mcp-context.json", artifact_root=tmp_path / "artifacts", run_id="gather-mcp-real")
    if not os.environ.get("FLYWHEEL_E2E_GATHER17_EXE"):
        assert result.status == "blocked"
        assert result.primary_outcome == "runtime_unavailable"
        return
    _assert_gather_result(result)


def test_altered_installed_source_is_blocked_against_pinned_wheel(tmp_path, monkeypatch):
    wheel = _wheel_from_current_runtime(tmp_path)
    if wheel is None:
        return
    clone_gather = _install_clone(tmp_path, wheel)
    source_file = clone_gather.parent.parent / "Lib/site-packages/gather/context.py"
    if not source_file.exists():
        source_file = clone_gather.parent.parent / "lib/python3.12/site-packages/gather/context.py"
    source_file.write_text(source_file.read_text(encoding="utf-8") + "\n# altered by e2e control\n", encoding="utf-8")
    monkeypatch.setenv("FLYWHEEL_E2E_GATHER17_EXE", str(clone_gather))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    result = run_journey(FIXTURE_DIR / "gather-cli-context.json", artifact_root=tmp_path / "artifacts", run_id="altered-source")

    assert result.status == "blocked"
    assert result.primary_outcome == "installed_file_mismatch"


def test_altered_installed_executable_is_blocked_by_expected_hash(tmp_path, monkeypatch):
    wheel = _wheel_from_current_runtime(tmp_path)
    if wheel is None:
        return
    clone_gather = _install_clone(tmp_path, wheel)
    expected_exe_hash = hashlib.sha256(clone_gather.read_bytes()).hexdigest()
    manifest = _manifest_with_expected_exe(tmp_path, expected_exe_hash)
    clone_gather.write_bytes(clone_gather.read_bytes() + b"\nmutation")
    monkeypatch.setenv("FLYWHEEL_E2E_GATHER17_EXE", str(clone_gather))
    monkeypatch.delenv("PYTHONPATH", raising=False)

    result = run_journey(manifest, artifact_root=tmp_path / "artifacts", repo_root=manifest.parent, run_id="altered-exe")

    assert result.status == "blocked"
    assert result.primary_outcome == "runtime_executable_hash_mismatch"
