"""Role-neutral runtime facts staged for benchmark providers."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA = "harness.cross-harness-runtime-context/v1"


def build_runtime_context(task: dict[str, Any], row: dict[str, Any], observed: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "required_json_fields": list(task.get("oracle", {}).get("required_json_fields", [])),
        "expected_artifacts": list(task.get("expected_artifacts", [])),
        "harness_values": {
            "task_id": row["task_id"], "input_sha256s": observed, "receipt_input_sha256s": observed,
            "raw_prompt_sha256": row["raw_prompt_sha256"], "tool_policy_sha256": row["tool_policy_sha256"],
            "raw_artifact_path": "output.txt", "receipt_path": "provider-receipt.json", "failure_modes": [],
            "orthogonal_states": {"execution_state": "returned", "oracle_state": "not_run", "receipt_state": "not_emitted"},
        },
    }


def stage_runtime_context(workspace: Path, attempt: Path, task: dict[str, Any], row: dict[str, Any],
                          observed: dict[str, str]) -> tuple[dict[str, Any], Path]:
    context = build_runtime_context(task, row, observed)
    encoded = (json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    context_path = attempt / "benchmark-context.json"; context_path.write_bytes(encoded)
    workspace.chmod(0o700); context_dir = workspace / "benchmark"; context_dir.mkdir()
    workspace_context = context_dir / "context.json"; workspace_context.write_bytes(encoded)
    workspace_context.chmod(0o600); context_dir.chmod(0o700); workspace.chmod(0o700)
    return context, context_path
