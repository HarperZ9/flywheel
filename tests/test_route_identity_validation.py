import hashlib

import pytest

from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_cli import _admission_identity_code
from harness.cross_harness_executor import SHARED_TOOL_POLICY, comparison_key, execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult
from scripts.run_harness_comparison_report import metric_rows_from_artifact


class InvalidObservationAdapter:
    role = "codex_harness"
    adapter_id = "codex_cli_json/v1"

    def enforcement(self, _request):
        description = {"boundary": "fixture"}
        return EnforcementResult(description, canonical_sha256(description), "fixture", "non_equivalent")

    def availability(self, _request):
        return AvailabilityResult(True, "", "ready", {})

    def execute(self, _request):
        return AdapterResult("returned", '{"artifacts":{}}', [], 1, "requested", "unsupported", "", "", {}, {}, [], [],
                             model_observation_basis="unknown")


def _execution_fixture(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    prompt = "prompt"
    manifest = {"task_set_id": "set", "task_rows": [{"task_id": "task", "raw_prompt": prompt,
        "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [],
        "expected_artifacts": [], "oracle": {}}], "provider_specs": [{"provider_role": "codex_harness",
        "harness_id": "codex", "adapter_id": "codex_cli_json/v1", "model_id": "stable",
        "model_display_name": "Stable", "requested_model_reference": "requested"}]}
    runtime = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True, "blocking_gates": []}]}
    return source, manifest, runtime


def test_execution_rejects_nonempty_observation_with_unknown_basis(tmp_path):
    source, manifest, runtime = _execution_fixture(tmp_path)
    row = execute_cross_harness_manifest(manifest, runtime, {"codex_harness": InvalidObservationAdapter()},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="spark",
        selectors=["task"], roles=["codex_harness"], repetitions=1)["rows"][0]
    assert (row["execution_state"], row["failure_class"]) == ("malformed", "invalid_model_observation")
    assert (row["model_observed"], row["model_observation_basis"]) == ("", "unknown")


def _admission_fixture():
    task = {"raw_prompt_sha256": "p", "input_sha256s": {}, "oracle": {}}
    spec = {"model_id": "stable", "requested_model_reference": "requested", "harness_id": "codex", "adapter_id": "adapter"}
    manifest = {"task_set_id": "set"}
    current = {"source_commit": "commit", "source_snapshot_sha256": "source", "cache_state": "cold",
               "execution_mode": "focused_run"}
    row = {"raw_prompt_sha256": "p", "input_sha256s": {}, "availability_evidence": {"adapter_evidence": {
        "oracle_spec_sha256": canonical_sha256({})}}, "model_id": "stable", "requested_model_reference": "requested",
        "harness_id": "codex", "adapter_id": "adapter", "tool_policy_sha256": canonical_sha256(SHARED_TOOL_POLICY),
        "source_commit": "commit", "source_snapshot_sha256": "source", "cache_state": "cold", "task_set_id": "set",
        "execution_mode": "focused_run", "provider_role": "codex_harness"}
    return row, task, spec, manifest, current


@pytest.mark.parametrize(("observed", "basis"), [
    ("requested", "unknown"), ("", "structured_provider_event"), ("requested", "unsupported"),
])
def test_admission_independently_rejects_invalid_observation_pairs(observed, basis):
    row, task, spec, manifest, current = _admission_fixture()
    row.update(model_observed=observed, model_observation_basis=basis)
    assert _admission_identity_code(row, task, spec, manifest, current, {}) == "admission_model_observation_invalid"


def test_comparison_independently_rejects_invalid_v2_observation_pair():
    row = {"phase": "spark", "provider_role": "codex_harness", "task_id": "task", "repetition": 1,
        "model_id": "stable", "model_display_name": "Stable", "requested_model_reference": "requested",
        "model_observed": "requested", "model_observation_basis": "unknown", "tool_policy_sha256": "a" * 64}
    row["comparison_key"] = comparison_key(row)
    with pytest.raises(ValueError, match="invalid model observation"):
        metric_rows_from_artifact({"schema": "harness.cross-harness-task-scorecard/v1", "rows": [row]}, "rows.json")
