import json
import os
import subprocess
import sys
from pathlib import Path

from harness.e2e_journey_manifest import MANIFEST_SCHEMA


def _manifest(source: Path) -> Path:
    fixtures = source / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.txt").write_text("E2E_SENTINEL_ALPHA\n\nE2E_SENTINEL_BETA\n", encoding="utf-8")
    path = source / "journey.json"
    path.write_text(json.dumps({
        "schema": MANIFEST_SCHEMA,
        "journey_id": "gather-context-selection-cli-private-temp-v1",
        "product": "gather",
        "product_version": "1.7.0",
        "runtime": {"kind": "browser", "executable_env": "NOPE", "expected_distribution": "gather-engine", "expected_version_prefix": "1.7."},
        "allowed_resource_paths": ["fixtures"],
        "fixtures": {"source_text": "fixtures/sample.txt"},
        "oracle": {"kind": "gather_context_selection/v1", "include_text": "E2E_SENTINEL_ALPHA", "exclude_text": "E2E_SENTINEL_BETA", "start_marker": "E2E_SENTINEL_ALPHA", "end_marker": "E2E_SENTINEL_BETA"},
    }), encoding="utf-8")
    return path


def test_cli_validate_and_run_emit_json_without_runtime_success_claim(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = _manifest(source)

    validate = subprocess.run([sys.executable, "-m", "harness.e2e_cli", "validate", str(path), "--source-root", str(source)], text=True, capture_output=True)
    assert validate.returncode == 0, validate.stderr
    assert json.loads(validate.stdout)["status"] == "valid"

    run = subprocess.run([sys.executable, "-m", "harness.e2e_cli", "run", str(path), "--source-root", str(source), "--artifact-root", str(tmp_path / "artifacts"), "--run-id", "cli-run"], text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    payload = json.loads(run.stdout)
    assert payload["status"] == "blocked"
    assert payload["primary_outcome"] == "runtime_unsupported"

    strict = subprocess.run([sys.executable, "-m", "harness.e2e_cli", "run", str(path), "--source-root", str(source), "--artifact-root", str(tmp_path / "strict-artifacts"), "--run-id", "strict-run", "--strict"], text=True, capture_output=True)
    assert strict.returncode == 1
    strict_payload = json.loads(strict.stdout)
    assert strict_payload["primary_outcome"] == "runtime_unsupported"


def test_packaged_cli_entry_dispatches_e2e_journey(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = _manifest(source)

    run = subprocess.run([sys.executable, "-m", "harness.cli_entry", "e2e-journey", "validate", str(path), "--source-root", str(source)], text=True, capture_output=True)

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["schema"] == "flywheel.product-e2e-journey/v1"


def test_checked_in_manifest_run_from_repo_root_stays_bounded(tmp_path):
    repo_root = Path.cwd()
    manifest = repo_root / "tests/fixtures/e2e/gather_context/gather-cli-context.json"
    env = os.environ.copy()
    env.pop("FLYWHEEL_E2E_GATHER17_EXE", None)
    env.pop("PYTHONPATH", None)

    run = subprocess.run([
        sys.executable, "-m", "harness.e2e_cli", "run", str(manifest),
        "--artifact-root", str(tmp_path / "artifacts"),
        "--run-id", "repo-root-bounded", "--strict",
    ], cwd=repo_root, env=env, text=True, capture_output=True, timeout=15)

    assert run.returncode == 1
    payload = json.loads(run.stdout)
    assert payload["status"] == "blocked"
    assert payload["primary_outcome"] == "runtime_unavailable"
    snapshots = json.loads(Path(payload["artifacts"]["source_snapshots"]).read_text(encoding="utf-8"))
    before_files = {row["path"] for row in snapshots["before"]["files"]}
    assert before_files == {
        "tests/fixtures/e2e/gather_context/gather-cli-context.json",
        "tests/fixtures/e2e/gather_context/sample.txt",
    }
    assert "harness/e2e_runner.py" not in before_files
    assert "tests/fixtures/e2e/gather_context/gather-mcp-context.json" not in before_files
