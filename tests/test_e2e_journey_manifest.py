import json
from pathlib import Path

import pytest

from harness.e2e_journey_manifest import MANIFEST_SCHEMA, load_journey_manifest
from harness.e2e_runner import run_journey


def _source_with_manifest(tmp_path, *, runtime_kind="cli_process", source_text="fixtures/sample.txt", allowed=None):
    source = tmp_path / "source"
    fixtures = source / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "sample.txt").write_text("E2E_SENTINEL_ALPHA\n\nE2E_SENTINEL_BETA\n", encoding="utf-8")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "journey_id": "gather-context-selection-cli-private-temp-v1",
        "product": "gather",
        "product_version": "1.7.0",
        "platforms": ["windows"],
        "runtime": {
            "kind": runtime_kind,
            "executable_env": "FLYWHEEL_E2E_GATHER17_EXE",
            "expected_distribution": "gather-engine",
            "expected_version_prefix": "1.7.",
            "forbid_pythonpath": True,
            "forbid_editable": True,
        },
        "allowed_resource_paths": allowed or ["fixtures"],
        "fixtures": {"source_text": source_text},
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
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return source, path


def test_manifest_loads_schema_and_resolves_operator_owned_fixture(tmp_path):
    source, path = _source_with_manifest(tmp_path)

    manifest = load_journey_manifest(path, repo_root=source)

    assert manifest.schema == MANIFEST_SCHEMA
    assert manifest.runtime.kind == "cli_process"
    assert manifest.fixture_path("source_text") == (source / "fixtures/sample.txt").resolve()


def test_manifest_rejects_fixture_outside_allowed_resource_paths(tmp_path):
    source, path = _source_with_manifest(tmp_path, source_text="outside.txt")
    (source / "outside.txt").write_text("private", encoding="utf-8")

    with pytest.raises(ValueError, match="outside allowed_resource_paths"):
        load_journey_manifest(path, repo_root=source)


def test_manifest_rejects_unknown_schema(tmp_path):
    source, path = _source_with_manifest(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = "flywheel.product-e2e-journey/v9"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported journey schema"):
        load_journey_manifest(path, repo_root=source)


def test_future_runtime_is_retained_as_blocked_denominator(tmp_path):
    source, path = _source_with_manifest(tmp_path, runtime_kind="browser")

    result = run_journey(path, artifact_root=tmp_path / "artifacts", repo_root=source, run_id="run-browser")

    assert result.status == "blocked"
    assert result.primary_outcome == "runtime_unsupported"
    assert result.runtime["kind"] == "browser"
    assert result.oracle["status"] == "not_run"
    assert Path(result.artifacts["run_result"]).is_file()
