from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.cross_harness_adapters import _enforcement
from harness.cross_harness_artifacts import materialize_response_envelope
from harness.cross_harness_executor import execute_cross_harness_manifest
from harness.cross_harness_manifest import build_manifest, load_json
from harness.cross_harness_types import AdapterResult, AvailabilityResult


ROOT = Path(__file__).resolve().parent.parent


class ContextReadingAdapter:
    role = "codex_harness"
    adapter_id = "codex_cli_json/v1"

    def __init__(self) -> None:
        self.context: dict = {}

    def enforcement(self, _request):
        return _enforcement({"boundary": "test_read_only"})

    def availability(self, _request):
        return AvailabilityResult(True, "", "available", {"provider_called": False})

    def execute(self, request):
        context_path = request.workspace_root / "benchmark" / "context.json"
        self.context = json.loads(context_path.read_text(encoding="utf-8"))
        fixture = json.loads(
            (request.workspace_root / "benchmarks" / "fixtures" / "cross-harness" / "index-events-v1.json").read_text(
                encoding="utf-8"
            )
        )
        classes, citations = [], []
        for event in fixture["events"]:
            if event.get("type") == "mcp_call" and event.get("outcome") == "failure":
                classes.append("live_mcp_failure")
            elif event.get("type") == "artifact_read" and event.get("source") == "stale":
                classes.append("stale_artifact_use")
            elif event.get("type") == "json_parse" and event.get("outcome") == "failure":
                classes.append("invalid_json")
            elif event.get("type") == "match" and event.get("mode") == "degraded":
                classes.append("degraded_match")
            else:
                continue
            citations.append(event["event_id"])
        values = self.context["harness_values"]
        report = {
            "task_id": values["task_id"],
            "input_sha256s": values["input_sha256s"],
            "receipt_input_sha256s": values["receipt_input_sha256s"],
            "failure_classes": sorted(classes),
            "cited_event_ids": sorted(citations),
        }
        output = json.dumps(
            {
                "artifacts": {
                    "index_fallback_integrity_report.json": report,
                    "index_fallback_integrity_report.md": f"# {request.task_id}\n\nFixture-derived result.",
                }
            },
            separators=(",", ":"),
        )
        return AdapterResult(
            "returned", output, [], 7, request.requested_model_reference, "unsupported",
            "", "", {}, {}, [], [], "structured_provider_event",
        )


def _manifest():
    return build_manifest(
        load_json(ROOT / "benchmarks" / "agentic-task-set-v1.json"),
        load_json(ROOT / "benchmarks" / "cross-harness-adapter-contract-v2.json"),
        source_root=str(ROOT),
        provider_roles=["codex_harness"],
    )


def _runtime():
    return {
        "runtime_rows": [
            {
                "provider_role": "codex_harness",
                "focused_run_ready": True,
                "blocking_gates": [],
                "endpoint_profile_matches": [],
                "endpoint_gate_matches": [],
            }
        ]
    }


def test_manifest_prompt_requires_role_neutral_runtime_context_and_compact_json():
    prompt = next(row for row in _manifest()["task_rows"] if row["task_id"].startswith("agt-001"))["raw_prompt"]
    assert "benchmark/context.json" in prompt
    assert "Do not run commands" in prompt
    assert "one compact JSON object on one line" in prompt
    assert "codex_harness" not in prompt and "flywheel_harness" not in prompt


def test_executor_stages_receipt_bound_role_neutral_runtime_context(tmp_path):
    adapter = ContextReadingAdapter()
    run = execute_cross_harness_manifest(
        _manifest(), _runtime(), {"codex_harness": adapter}, artifact_root=tmp_path / "artifacts",
        source_root=ROOT, run_id="runtime-context", phase="admission-smoke", selectors=["agt-001"],
        roles=["codex_harness"], repetitions=1, source_commit="test-commit",
    )
    row = run["rows"][0]
    assert (row["primary_outcome"], row["oracle_state"], row["receipt_state"]) == ("completed", "pass", "verified")
    values = adapter.context["harness_values"]
    assert adapter.context["schema"] == "harness.cross-harness-runtime-context/v1"
    assert values["raw_prompt_sha256"] == row["raw_prompt_sha256"]
    assert values["tool_policy_sha256"] == row["tool_policy_sha256"]
    assert values["input_sha256s"] == row["input_sha256s"]
    receipt = json.loads(Path(row["receipt_path"]).read_text(encoding="utf-8"))
    assert "benchmark-context.json" in {item["name"] for item in receipt["receipt_subject"]["artifacts"]}


def test_runtime_context_name_is_reserved_from_provider_artifacts(tmp_path):
    with pytest.raises(ValueError, match="standard attempt filename"):
        materialize_response_envelope(
            '{"artifacts":{"benchmark-context.json":{}}}', ["benchmark-context.json"], tmp_path,
        )
