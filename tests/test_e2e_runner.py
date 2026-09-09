import json
import hashlib
from pathlib import Path

from harness.e2e_journey_manifest import MANIFEST_SCHEMA
from harness.e2e_runner import JourneyRunResult, run_journey


EXPECTED_SELECTED = "E2E_SENTINEL_ALPHA selected body."
EXPECTED_SELECTED_SHA = hashlib.sha256(EXPECTED_SELECTED.encode("utf-8")).hexdigest()


def _write_manifest(source: Path, *, runtime_kind="cli_process", env_name="MISSING_GATHER_EXE") -> Path:
    fixtures = source / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.txt").write_text(
        "Title\n\nE2E_SENTINEL_ALPHA selected body.\n\nE2E_SENTINEL_BETA wrong body.\n",
        encoding="utf-8",
    )
    data = {
        "schema": MANIFEST_SCHEMA,
        "journey_id": "gather-context-selection-cli-private-temp-v1",
        "product": "gather",
        "product_version": "1.7.0",
        "runtime": {
            "kind": runtime_kind,
            "executable_env": env_name,
            "expected_distribution": "gather-engine",
            "expected_version_prefix": "1.7.",
            "forbid_pythonpath": True,
            "forbid_editable": True,
        },
        "allowed_resource_paths": ["fixtures"],
        "fixtures": {"source_text": "fixtures/sample.txt"},
        "oracle": {
            "kind": "gather_context_selection/v1",
            "include_text": "E2E_SENTINEL_ALPHA",
            "exclude_text": "E2E_SENTINEL_BETA",
            "start_marker": "E2E_SENTINEL_ALPHA",
            "end_marker": "E2E_SENTINEL_BETA",
        },
        "controls": ["wrong_body", "tamper_refusal"],
    }
    path = source / "journey.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_runtime_is_blocked_with_receipt_and_denominator(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = _write_manifest(source)
    monkeypatch.delenv("MISSING_GATHER_EXE", raising=False)

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="run-missing")

    assert result.status == "blocked"
    assert result.primary_outcome == "runtime_unavailable"
    assert result.oracle["status"] == "not_run"
    assert Path(result.artifacts["run_result"]).is_file()
    assert Path(result.artifacts["artifact_index"]).is_file()


def test_completed_lifecycle_is_separate_from_wrong_body_oracle_failure(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = _write_manifest(source)

    def fake_flow(manifest, runtime, workspace, owner_state):
        return {
            "steps": [{"id": "select", "status": "completed"}],
            "expected_selection": {
                "text": "E2E_SENTINEL_ALPHA selected body.",
                "sha256": EXPECTED_SELECTED_SHA,
                "start": 7,
                "limit": 27,
            },
            "selected_payload": {
                "schema": "gather.readable-context/v1",
                "selection_digest": "a" * 64,
                "verified": True,
                "selections": [{"text": "E2E_SENTINEL_ALPHA selected body."}],
            },
            "wrong_body_payload": {
                "schema": "gather.readable-context/v1",
                "selection_digest": "b" * 64,
                "verified": True,
                "selections": [{"text": "E2E_SENTINEL_ALPHA selected body. E2E_SENTINEL_BETA wrong body."}],
            },
            "tamper_refusal": {"status": "pass", "evidence": "body status CORRUPT"},
        }

    monkeypatch.setenv("MISSING_GATHER_EXE", "C:/fake/gather.exe")
    monkeypatch.setattr("harness.e2e_runner._preflight_runtime", lambda manifest: {"status": "ready", "executable": "C:/fake/gather.exe", "version": "1.7.0", "source": "installed_wheel"})
    monkeypatch.setattr("harness.e2e_runner._run_gather_context_flow", fake_flow)

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="run-completed")

    assert isinstance(result, JourneyRunResult)
    assert result.status == "completed"
    assert result.oracle["status"] == "pass"
    assert result.semantic_status == "pass"
    assert result.calibration["wrong_body"]["status"] == "pass"
    assert result.calibration["wrong_body"]["oracle_status"] == "fail"
    assert Path(result.workspace_root).is_dir()


def test_oracle_failure_keeps_completed_lifecycle_but_semantic_fail(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = _write_manifest(source)

    def fake_flow(manifest, runtime, workspace, owner_state):
        return {
            "steps": [{"id": "select", "status": "completed"}],
            "expected_selection": {
                "text": "E2E_SENTINEL_ALPHA selected body.",
                "sha256": EXPECTED_SELECTED_SHA,
                "start": 7,
                "limit": 27,
            },
            "selected_payload": {
                "schema": "gather.readable-context/v1",
                "selection_digest": "c" * 64,
                "verified": True,
                "selections": [{"text": "E2E_SENTINEL_BETA wrong body."}],
            },
            "wrong_body_payload": None,
            "tamper_refusal": {"status": "not_run"},
        }

    monkeypatch.setattr("harness.e2e_runner._preflight_runtime", lambda manifest: {"status": "ready", "executable": "C:/fake/gather.exe", "version": "1.7.0", "source": "installed_wheel"})
    monkeypatch.setattr("harness.e2e_runner._run_gather_context_flow", fake_flow)

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="run-oracle-fail")

    assert result.status == "completed"
    assert result.oracle["status"] == "fail"
    assert result.semantic_status == "fail"
    assert result.primary_outcome == "semantic_fail"
    assert Path(result.workspace_root).is_dir()


def test_plausible_truncated_selection_fails_exact_span_oracle(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = _write_manifest(source)

    def fake_flow(manifest, runtime, workspace, owner_state):
        return {
            "steps": [{"id": "select", "status": "completed"}],
            "expected_selection": {
                "text": "E2E_SENTINEL_ALPHA selected body.",
                "sha256": EXPECTED_SELECTED_SHA,
                "start": 7,
                "limit": 27,
            },
            "selected_payload": {
                "schema": "gather.readable-context/v1",
                "selection_digest": "a" * 64,
                "verified": True,
                "selections": [{"text": "E2E_SENTINEL_ALPHA"}],
            },
            "wrong_body_payload": {
                "schema": "gather.readable-context/v1",
                "selection_digest": "b" * 64,
                "verified": True,
                "selections": [{"text": "E2E_SENTINEL_ALPHA selected body. E2E_SENTINEL_BETA wrong body."}],
            },
            "tamper_refusal": {"status": "pass", "evidence": "body status CORRUPT"},
        }

    monkeypatch.setattr("harness.e2e_runner._preflight_runtime", lambda manifest: {"status": "ready", "executable": "C:/fake/gather.exe", "version": "1.7.0", "source": "installed_wheel"})
    monkeypatch.setattr("harness.e2e_runner._run_gather_context_flow", fake_flow)

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="run-truncated")

    assert result.status == "completed"
    assert result.primary_outcome == "semantic_fail"
    assert result.oracle["status"] == "fail"
    assert "selection_text_mismatch" in result.oracle["failure_codes"]
    assert result.oracle["expected_selection_sha256"] != result.oracle["observed_selection_sha256"]


def test_source_snapshots_only_manifest_resources_and_manifest(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    path = _write_manifest(source)
    private_file = source / "private-sibling.txt"
    private_file.write_text("must not be read", encoding="utf-8")
    hidden_dir = source / ".scratch"
    hidden_dir.mkdir()
    hidden_private = hidden_dir / "secret.txt"
    hidden_private.write_text("must not be read", encoding="utf-8")
    guarded = {private_file.resolve(), hidden_private.resolve()}
    original_open = Path.open

    def guard_private_open(self, *args, **kwargs):
        if self.resolve(strict=False) in guarded:
            raise AssertionError(f"private sibling opened: {self}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard_private_open)
    monkeypatch.delenv("MISSING_GATHER_EXE", raising=False)

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="bounded")

    assert result.status == "blocked"
    snapshots = json.loads(Path(result.artifacts["source_snapshots"]).read_text(encoding="utf-8"))
    before_files = {row["path"] for row in snapshots["before"]["files"]}
    after_files = {row["path"] for row in snapshots["after"]["files"]}
    assert before_files == {"fixtures/sample.txt", "journey.json"}
    assert after_files == before_files
    assert "private-sibling.txt" not in before_files
    assert ".scratch/secret.txt" not in before_files
