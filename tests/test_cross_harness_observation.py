import hashlib

from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult


class UnattestedAdapter:
    role = "local_14b"
    adapter_id = "local_14b/v1"

    def enforcement(self, request):
        description = {"boundary": "fixture"}
        return EnforcementResult(description, canonical_sha256(description), "fixture", "non_equivalent")

    def availability(self, request):
        return AvailabilityResult(True, "", "ready", {})

    def execute(self, request):
        return AdapterResult("returned", '{"artifacts":{}}', [], 1, "untrusted-model", "unsupported", "", "", {}, {}, [], [],
                             model_observation_basis="unknown")


def test_returned_unattested_model_is_empty_and_records_request_limitation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    prompt = "prompt"
    manifest = {"task_set_id": "set", "task_rows": [{"task_id": "task", "raw_prompt": prompt,
        "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [],
        "expected_artifacts": [], "oracle": {}}], "provider_specs": [{"provider_role": "local_14b",
        "harness_id": "local", "adapter_id": "local_14b/v1", "model_id": "stable-model",
        "model_display_name": "Stable model", "requested_model_reference": "request-model"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": []}]}

    row = execute_cross_harness_manifest(manifest, runtime, {"local_14b": UnattestedAdapter()}, artifact_root=tmp_path / "artifacts",
        source_root=source, run_id="run", phase="local", selectors=["task"], roles=["local_14b"], repetitions=1)["rows"][0]

    assert row["requested_model_reference"] == "request-model"
    assert (row["model_observed"], row["model_observation_basis"]) == ("", "unknown")
    assert "provider_request_accepted_not_model_attested" in row["limitations"]
