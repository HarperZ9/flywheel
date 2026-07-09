"""Non-executing manifest projection for the custom agentic task set."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "harness.agentic-task-manifest/v1"
SCORECARD_SCHEMA = "harness.agentic-task-scorecard/v1"
DEFAULT_ARTIFACT_DIR = "C:/tmp/agentic_task_runs"
DEFAULT_PROVIDER_ROLES = ["dry"]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def validate_task_set(task_set: dict[str, Any], adapter: dict[str, Any]) -> None:
    _require(task_set, ["schema", "task_set_id", "metrics", "lanes", "tasks"], "task set")
    _require(adapter, ["schema", "adapter_id", "task_benchmark_map"], "adapter")
    if task_set.get("schema") != "harness.agentic-task-set/v1":
        raise ValueError(f"unsupported task-set schema: {task_set.get('schema')}")
    if adapter.get("schema") != "harness.agentic-task-set-adapter/v1":
        raise ValueError(f"unsupported adapter schema: {adapter.get('schema')}")
    tasks = task_set.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task set must contain at least one task")
    mapping = adapter.get("task_benchmark_map")
    if not isinstance(mapping, dict):
        raise ValueError("adapter task_benchmark_map must be an object")
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"task {index} must be an object")
        _require(
            task,
            ["id", "lane", "difficulty", "prompt", "required_inputs", "expected_artifacts", "scoring_focus", "must_not"],
            f"task {index}",
        )
        task_id = str(task["id"])
        if task_id in seen:
            raise ValueError(f"duplicate task id: {task_id}")
        seen.add(task_id)
        if task_id not in mapping:
            raise ValueError(f"task missing adapter benchmark mapping: {task_id}")


def build_manifest(
    task_set: dict[str, Any],
    adapter: dict[str, Any],
    *,
    run_id: str = "",
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
    provider_roles: list[str] | None = None,
    task_set_path: str = "",
    adapter_path: str = "",
    task_set_sha256: str = "",
    adapter_sha256: str = "",
) -> dict[str, Any]:
    validate_task_set(task_set, adapter)
    provider_roles = provider_roles or list(DEFAULT_PROVIDER_ROLES)
    task_rows = [
        _task_row(task_set, adapter, task, artifact_dir=artifact_dir)
        for task in task_set["tasks"]
    ]
    scorecard_rows = [
        _scorecard_row(row, provider_role=provider_role, artifact_dir=artifact_dir)
        for provider_role in provider_roles
        for row in task_rows
    ]
    benchmark_ids = sorted({row["benchmark_id"] for row in task_rows})
    dataset_lanes = sorted({row["dataset_lane"] for row in task_rows})
    coverage_units = [row["coverage_unit"] for row in task_rows]
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "status": "planned_not_executed",
        "run_id": run_id,
        "task_set_id": task_set["task_set_id"],
        "task_set_path": task_set_path,
        "task_set_sha256": task_set_sha256,
        "adapter_id": adapter["adapter_id"],
        "adapter_path": adapter_path,
        "adapter_sha256": adapter_sha256,
        "planned_scorecard_schema": adapter.get("planned_scorecard_schema", SCORECARD_SCHEMA),
        "artifact_dir": artifact_dir,
        "provider_roles": provider_roles,
        "task_count": len(task_rows),
        "benchmark_ids": benchmark_ids,
        "dataset_lanes": dataset_lanes,
        "coverage_units": coverage_units,
        "metric_weights": task_set.get("metrics", []),
        "task_rows": task_rows,
        "dry_scorecard_rows": scorecard_rows,
        "non_execution_guards": list(adapter.get("non_execution_guards", [])) or [
            "The manifest must not call providers.",
            "The manifest must not probe endpoints.",
            "The manifest must not read model weights.",
            "The manifest must not infer benchmark success from task definitions.",
            "The manifest must not print secrets or payload bodies.",
        ],
        "summary": {
            "status": "planned_not_executed",
            "task_count": len(task_rows),
            "provider_roles": len(provider_roles),
            "planned_scorecard_rows": len(scorecard_rows),
            "benchmark_ids": len(benchmark_ids),
            "dataset_lanes": len(dataset_lanes),
            "coverage_units": len(coverage_units),
            "prompt_hashes": len({row["raw_prompt_sha256"] for row in task_rows}),
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
            "benchmark_execution": False,
        },
    }


def render_markdown(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# Agentic task manifest",
        "",
        f"- Schema: `{manifest['schema']}`",
        f"- Status: `{manifest['status']}`",
        f"- Task set: `{manifest['task_set_id']}`",
        f"- Adapter: `{manifest['adapter_id']}`",
        f"- Tasks: `{summary['task_count']}`",
        f"- Planned scorecard rows: `{summary['planned_scorecard_rows']}`",
        f"- Provider execution: `{str(summary['provider_execution']).lower()}`",
        f"- Endpoint probe: `{str(summary['endpoint_probe']).lower()}`",
        f"- Model weight read: `{str(summary['model_weight_read']).lower()}`",
        f"- Benchmark execution: `{str(summary['benchmark_execution']).lower()}`",
        "",
        "## Task rows",
        "",
        "| Task | Benchmark | Lane | Difficulty | Prompt hash | Planned artifacts |",
        "|---|---|---|---|---|---:|",
    ]
    for row in manifest["task_rows"]:
        lines.append(
            "| {task} | {benchmark} | {lane} | {difficulty} | `{hash}` | {artifacts} |".format(
                task=row["task_id"],
                benchmark=row["benchmark_id"],
                lane=row["dataset_lane"],
                difficulty=row["difficulty"],
                hash=row["raw_prompt_sha256"][:16],
                artifacts=len(row["planned_artifacts"]),
            )
        )
    lines.extend(["", "## Non-execution guards", ""])
    for guard in manifest.get("non_execution_guards", []):
        lines.append(f"- {guard}")
    return "\n".join(lines) + "\n"


def _require(obj: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def _prompt_text(task_set: dict[str, Any], task: dict[str, Any]) -> str:
    global_rules = task_set.get("global_rules", {})
    parts = [
        f"Task set: {task_set['task_set_id']}",
        f"Task id: {task['id']}",
        f"Lane: {task['lane']}",
        f"Difficulty: {task['difficulty']}",
        "",
        "Prompt:",
        str(task["prompt"]),
        "",
        "Required inputs:",
        *[f"- {item}" for item in task.get("required_inputs", [])],
        "",
        "Expected artifacts:",
        *[f"- {item}" for item in task.get("expected_artifacts", [])],
        "",
        "Scoring focus:",
        *[f"- {item}" for item in task.get("scoring_focus", [])],
        "",
        "Must not:",
        *[f"- {item}" for item in task.get("must_not", [])],
        "",
        "Global rules:",
        json.dumps(global_rules, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(parts).strip() + "\n"


def _task_row(task_set: dict[str, Any], adapter: dict[str, Any], task: dict[str, Any], *, artifact_dir: str) -> dict[str, Any]:
    prompt = _prompt_text(task_set, task)
    task_id = str(task["id"])
    benchmark_id = str(adapter["task_benchmark_map"][task_id])
    return {
        "schema": "harness.agentic-task-manifest.task/v1",
        "task_set_id": task_set["task_set_id"],
        "task_id": task_id,
        "benchmark_id": benchmark_id,
        "dataset_lane": str(task["lane"]),
        "coverage_unit": task_id,
        "difficulty": str(task["difficulty"]),
        "raw_prompt_sha256": sha256_text(prompt),
        "raw_prompt_bytes": len(prompt.encode("utf-8")),
        "raw_prompt_preview": prompt[:240],
        "required_inputs": list(task.get("required_inputs", [])),
        "expected_artifacts": list(task.get("expected_artifacts", [])),
        "scoring_focus": list(task.get("scoring_focus", [])),
        "must_not": list(task.get("must_not", [])),
        "planned_artifacts": _planned_artifacts(artifact_dir, "dry", task_id),
    }


def _scorecard_row(task_row: dict[str, Any], *, provider_role: str, artifact_dir: str) -> dict[str, Any]:
    planned = _planned_artifacts(artifact_dir, provider_role, task_row["task_id"])
    return {
        "schema": SCORECARD_SCHEMA,
        "task_set_id": task_row["task_set_id"],
        "task_id": task_row["task_id"],
        "benchmark_id": task_row["benchmark_id"],
        "coverage_unit": task_row["coverage_unit"],
        "provider_role": provider_role,
        "harness_id": "dry_null" if provider_role == "dry" else provider_role,
        "model_id": "none",
        "execution_mode": "manifest_only",
        "status": "planned",
        "failure_class": "not_executed",
        "raw_prompt_sha256": task_row["raw_prompt_sha256"],
        "raw_output_sha256": "",
        "raw_prompt_path": planned["prompt.txt"],
        "raw_output_path": planned["output.txt"],
        "receipt_path": planned["receipt.json"],
        "tool_trace_path": planned["tool_trace.json"],
        "metrics": {metric: None for metric in task_row["scoring_focus"]},
        "limitations": ["Manifest-only row; no provider, endpoint, or benchmark was executed."],
    }


def _planned_artifacts(artifact_dir: str, provider_role: str, task_id: str) -> dict[str, str]:
    base = Path(artifact_dir) / provider_role / task_id
    return {
        name: (base / name).as_posix()
        for name in ("prompt.txt", "output.txt", "tool_trace.json", "receipt.json", "metrics.json", "limitations.md")
    }
