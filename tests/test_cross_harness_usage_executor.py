import hashlib
import json

from harness.cross_harness_executor import execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult


USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


class UsageAdapter:
    role = "flywheel_harness"
    adapter_id = "flywheel_router/v1"

    def enforcement(self, _request):
        description = {"boundary": "fixture"}
        encoded = json.dumps(description, sort_keys=True, separators=(",", ":")).encode()
        return EnforcementResult(description, hashlib.sha256(encoded).hexdigest(), "fixture", "non_equivalent")

    def availability(self, _request):
        return AvailabilityResult(True, "", "ready", {})

    def execute(self, _request):
        trace = [{"source": "codex_inner", "inner_call": 1,
                  "type": "turn.completed", "usage": USAGE}]
        inflated = {"inner_calls": 1, "per_call": [USAGE],
                    "aggregate": {**USAGE, "total_tokens": 16}}
        return AdapterResult("returned", '{"artifacts":{}}', trace, 1, "model", "unsupported",
                             "", "", {}, inflated, [], [], "structured_provider_event")


def test_executor_refuses_usage_that_does_not_match_retained_trace_before_sealing(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    prompt = "prompt\n"
    manifest = {
        "task_set_id": "set",
        "task_rows": [{"task_id": "agt-001-task", "raw_prompt": prompt,
                       "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                       "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}],
        "provider_specs": [{"provider_role": "flywheel_harness", "harness_id": "flywheel",
                            "adapter_id": "flywheel_router/v1", "model_id": "model",
                            "model_display_name": "Model", "requested_model_reference": "model"}],
    }
    runtime = {"runtime_rows": [{"provider_role": "flywheel_harness", "focused_run_ready": True,
                                  "blocking_gates": [], "endpoint_profile_matches": [],
                                  "endpoint_gate_matches": []}]}
    run = execute_cross_harness_manifest(
        manifest, runtime, {"flywheel_harness": UsageAdapter()}, artifact_root=tmp_path / "artifacts",
        source_root=source, run_id="run", phase="spark", selectors=["agt-001"],
        roles=["flywheel_harness"], repetitions=1)

    row = run["rows"][0]
    assert row["metrics"]["usage"] == {}
    assert row["usage_verification"]["verified"] is False
    reason = row["usage_verification"]["usage_cell_refused"]
    assert reason.startswith("USAGE_RECOMPUTE_MISMATCH")
    assert row["metric_null_reasons"]["usage"] == reason
    receipt = json.loads((tmp_path / "artifacts/run/spark/flywheel_harness/agt-001-task/rep-001/receipt.json").read_text())
    assert receipt["receipt_subject"]["final_row"]["metrics"]["usage"] == {}
    assert receipt["receipt_subject"]["final_row"]["usage_verification"] == row["usage_verification"]
