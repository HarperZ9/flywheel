"""Non-executing cross-harness task manifest projection."""
from __future__ import annotations
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
SCHEMA, SCORECARD_SCHEMA, DEFAULT_ARTIFACT_DIR = "harness.cross-harness-manifest/v1", "harness.cross-harness-task-scorecard/v1", str(Path(tempfile.gettempdir()) / "cross_harness_runs")
def now_utc() -> str: return datetime.now(UTC).isoformat().replace("+00:00", "Z")
def sha256_text(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()
def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
def _object(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    if len(rows) != len(dict(rows)): raise ValueError("duplicate JSON key")
    return dict(rows)
def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_object)
    if not isinstance(value, dict): raise ValueError("JSON root must be an object")
    return value
def split_csv(value: str) -> list[str]: return [part.strip() for part in value.split(",") if part.strip()]
def provider_roles_from_contract(contract: dict[str, Any]) -> list[str]:
    rows = contract.get("provider_roles") if isinstance(contract.get("provider_roles"), list) else []
    return [str(row.get("provider_role", "")) for row in rows if isinstance(row, dict) and row.get("provider_role")]
def validate_inputs(task_set: dict[str, Any], contract: dict[str, Any], provider_roles: list[str]) -> None:
    _require(task_set, ["schema", "task_set_id", "tasks"], "task set")
    _require(contract, ["schema", "contract_id", "provider_roles", "scorecard_row_contract"], "contract")
    if task_set.get("schema") != "harness.agentic-task-set/v1":
        raise ValueError(f"unsupported task-set schema: {task_set.get('schema')}")
    if contract.get("schema") != "harness.cross-harness-adapter-contract/v2":
        raise ValueError(f"unsupported cross-harness contract schema: {contract.get('schema')}")
    tasks = task_set.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task set must contain at least one task")
    available = set(provider_roles_from_contract(contract))
    missing = sorted(set(provider_roles) - available)
    if missing:
        raise ValueError(f"unknown cross-harness provider roles: {', '.join(missing)}")
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"task {index} must be an object")
        _require(
            task,
            ["id", "lane", "difficulty", "prompt", "required_inputs", "expected_artifacts", "scoring_focus", "must_not"],
            f"task {index}",
        )
def build_manifest(
    task_set: dict[str, Any],
    contract: dict[str, Any],
    *,
    run_id: str = "",
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
    provider_roles: list[str] | None = None,
    task_set_path: str = "", contract_path: str = "", source_root: str = "",
    task_set_sha256: str = "", contract_sha256: str = "",
) -> dict[str, Any]:
    provider_roles = provider_roles or provider_roles_from_contract(contract)
    validate_inputs(task_set, contract, provider_roles)
    try: source = Path(source_root).resolve(strict=True) if source_root else None
    except OSError as exc: raise ValueError("source root is unavailable") from exc
    if source is not None and not source.is_dir(): raise ValueError("source root is not a directory")
    provider_specs = _provider_specs(contract, provider_roles)
    task_rows = [_task_row(task_set, contract, task, artifact_dir=artifact_dir, source_root=source) for task in task_set["tasks"]]
    scorecard_rows = [_scorecard_row(task_row, provider_specs[provider_role], provider_role=provider_role, artifact_dir=artifact_dir)
                      for provider_role in provider_roles for task_row in task_rows]
    required_metrics = _required_metrics(contract)
    dataset_lanes = sorted({"cross_harness_reproducibility"} | {
        str(row.get("source_task_lane", ""))
        for row in task_rows
        if row.get("source_task_lane")
    })
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "status": "planned_not_executed",
        "run_id": run_id,
        "contract_id": contract["contract_id"],
        "contract_schema": contract["schema"],
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "task_set_id": task_set["task_set_id"],
        "task_set_path": task_set_path,
        "task_set_sha256": task_set_sha256,
        "planned_scorecard_schema": contract.get("planned_scorecard_schema", SCORECARD_SCHEMA),
        "planned_run_receipt_schema": contract.get("planned_run_receipt_schema", ""),
        "artifact_dir": artifact_dir,
        "provider_roles": provider_roles,
        "provider_specs": [provider_specs[role] for role in provider_roles],
        "benchmark_id": "cross_harness_reproducibility_matrix",
        "benchmark_ids": ["cross_harness_reproducibility_matrix"],
        "dataset_lanes": dataset_lanes,
        "coverage_units": [row["coverage_unit"] for row in task_rows],
        "required_metrics": required_metrics,
        "comparability_checks": list(contract.get("comparability_checks", [])),
        "global_invariants": list(contract.get("global_invariants", [])),
        "task_count": len(task_rows),
        "task_rows": task_rows,
        "dry_scorecard_rows": scorecard_rows,
        "non_execution_guards": [
            "The manifest must not call providers.",
            "The manifest must not probe endpoints.",
            "The manifest must not read model weights.",
            "The manifest must not infer benchmark success from planned rows.",
            "The manifest must not copy secrets, .env values, tokens, private keys, or private payload bodies.",
        ],
        "summary": {
            "status": "planned_not_executed",
            "task_count": len(task_rows),
            "provider_roles": len(provider_roles),
            "planned_scorecard_rows": len(scorecard_rows),
            "benchmark_id": "cross_harness_reproducibility_matrix",
            "coverage_units": len(task_rows),
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
        "# Cross-harness manifest",
        "",
        f"- Schema: `{manifest['schema']}`",
        f"- Status: `{manifest['status']}`",
        f"- Contract: `{manifest['contract_id']}`",
        f"- Task set: `{manifest['task_set_id']}`",
        f"- Benchmark id: `{manifest['benchmark_id']}`",
        f"- Tasks: `{summary['task_count']}`",
        f"- Provider roles: `{summary['provider_roles']}`",
        f"- Planned scorecard rows: `{summary['planned_scorecard_rows']}`",
        f"- Provider execution: `{str(summary['provider_execution']).lower()}`",
        f"- Endpoint probe: `{str(summary['endpoint_probe']).lower()}`",
        f"- Model weight read: `{str(summary['model_weight_read']).lower()}`",
        f"- Benchmark execution: `{str(summary['benchmark_execution']).lower()}`",
        "",
        "## Provider roles",
        "",
        "| Provider role | Harness | Target model | Adapter state | Allowed modes |",
        "|---|---|---|---|---|",
    ]
    for row in manifest["provider_specs"]:
        lines.append(
            "| {role} | {harness} | {model} | {state} | {modes} |".format(
                role=row["provider_role"],
                harness=row["harness_id"],
                model=row["model_display_name"],
                state=row["adapter_state"],
                modes=", ".join(row.get("allowed_modes", [])),
            )
        )
    lines.extend([
        "",
        "## Task rows",
        "",
        "| Task | Source lane | Prompt hash | Planned artifacts |",
        "|---|---|---|---:|",
    ])
    for row in manifest["task_rows"]:
        lines.append(
            "| {task} | {lane} | `{hash}` | {artifacts} |".format(
                task=row["task_id"],
                lane=row["source_task_lane"],
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
def _provider_specs(contract: dict[str, Any], provider_roles: list[str]) -> dict[str, dict[str, Any]]:
    rows = contract.get("provider_roles") if isinstance(contract.get("provider_roles"), list) else []
    specs = {
        str(row.get("provider_role", "")): {
            "provider_role": str(row.get("provider_role", "")),
            "harness_id": str(row.get("harness_id", "")),
            "model_id": str(row.get("model_id", "")), "model_display_name": str(row.get("model_display_name", "")),
            "requested_model_reference": str(row.get("requested_model_reference", "")),
            "adapter_id": str(row.get("adapter_id", "")),
            "endpoint_selector": dict(row.get("endpoint_selector", {})) if isinstance(row.get("endpoint_selector"), dict) else {},
            "adapter_state": str(row.get("adapter_state", "")),
            "allowed_modes": [str(item) for item in row.get("allowed_modes", []) if item]
            if isinstance(row.get("allowed_modes"), list)
            else [],
            "required_receipts": [str(item) for item in row.get("required_receipts", []) if item]
            if isinstance(row.get("required_receipts"), list)
            else [],
        }
        for row in rows
        if isinstance(row, dict) and row.get("provider_role")
    }
    return {role: specs[role] for role in provider_roles}
def _required_metrics(contract: dict[str, Any]) -> list[str]:
    row_contract = contract.get("scorecard_row_contract") if isinstance(contract.get("scorecard_row_contract"), dict) else {}
    return [str(metric) for metric in row_contract.get("required_metrics", []) if metric]
def _input_hashes(root: Path, inputs: list[Any], pilot: bool) -> dict[str, str]:
    hashes, root = {}, root.resolve()
    for item in inputs:
        ref, relative = str(item), Path(str(item))
        if "://" in ref:
            scheme, _, payload = ref.partition("://"); typed = Path(payload)
            if pilot or scheme not in {"workspace", "external", "operator"} or not payload or payload != payload.strip() or payload.startswith(("/", "\\")) or len(payload) > 1 and payload[0].isalpha() and payload[1] == ":" or typed.is_absolute() or typed.drive or ".." in typed.parts or str(typed).replace("\\", "/") != payload: raise ValueError(f"required input typed reference invalid: {ref}")
            continue
        path = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"required input is not a repo-relative file: {ref}")
        hashes[ref] = file_sha256(path)
    return hashes
def _prompt_text(task_set: dict[str, Any], contract: dict[str, Any], task: dict[str, Any]) -> str:
    envelope = {"artifacts": {
        name: "<markdown string>" if str(name).endswith(".md") else "<JSON object>"
        for name in task.get("expected_artifacts", [])
    }}
    parts = [
        f"Task set: {task_set['task_set_id']}",
        f"Task id: {task['id']}",
        f"Cross-harness contract: {contract['contract_id']}",
        f"Source lane: {task['lane']}",
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
        "Cross-harness invariants:",
        *[f"- {item}" for item in contract.get("global_invariants", [])],
        "",
        "Response envelope (JSON only):",
        json.dumps(envelope, sort_keys=True, separators=(",", ":")),
    ]
    return "\n".join(parts).strip() + "\n"
def _task_row(task_set: dict[str, Any], contract: dict[str, Any], task: dict[str, Any], *, artifact_dir: str, source_root: Path | None) -> dict[str, Any]:
    prompt, task_id = _prompt_text(task_set, contract, task), str(task["id"])
    oracle_contract, oracle = task_set.get("oracle_contract", {}), dict(task.get("oracle", {}))
    pilots = {"index_fallback_integrity/v1": "agt-001-index-fallback-integrity", "shared_task_artifact/v1": "agt-003-codex-flywheel-shared-task", "paired_friction/v1": "agt-009-receipts-vs-guardrails-friction", "documentation_maintenance/v1": "agt-010-documentation-schematic-maintenance"}
    checker_id = oracle.get("checker_id")
    if (checker_id in pilots and task_id != pilots[checker_id]) or (task_id in pilots.values() and pilots.get(checker_id) != task_id): raise ValueError("registered checker and canonical task id must pair")
    inputs = list(task.get("required_inputs", []))
    if source_root is None and any("://" not in str(item) for item in inputs): raise ValueError("source root is required for repo-relative inputs")
    root = source_root or Path.cwd()
    input_sha256s, artifacts = _input_hashes(root, inputs, checker_id in pilots), list(task.get("expected_artifacts", []))
    checker = oracle_contract.get("checkers", {}).get(oracle.get("checker_id"), {})
    return {
        "schema": "harness.cross-harness-manifest.task/v1",
        "task_set_id": task_set["task_set_id"],
        "task_id": task_id,
        "benchmark_id": "cross_harness_reproducibility_matrix",
        "coverage_unit": task_id,
        "dataset_lane": "cross_harness_reproducibility",
        "source_task_lane": str(task["lane"]),
        "difficulty": str(task["difficulty"]),
        "raw_prompt": prompt,
        "raw_prompt_sha256": sha256_text(prompt),
        "raw_prompt_bytes": len(prompt.encode("utf-8")),
        "raw_prompt_preview": prompt[:240],
        "required_inputs": inputs,
        "input_sha256s": input_sha256s,
        "expected_artifacts": artifacts,
        "oracle": {
            **checker, **oracle, "expected_artifacts": artifacts,
            "contract_version": oracle_contract.get("version", ""),
            "common_predicates": oracle_contract.get("common_predicates", []),
            "common_failure_codes": oracle_contract.get("common_failure_codes", []),
        },
        "response_envelope": {
            "type": "json_object",
            "artifacts": {
                name: "markdown_string" if str(name).endswith(".md") else "json_object"
                for name in artifacts
            },
            "additional_properties": False,
        },
        "scoring_focus": list(task.get("scoring_focus", [])),
        "must_not": list(task.get("must_not", [])),
        "planned_artifacts": _planned_artifacts(artifact_dir, "dry", task_id),
    }
def _scorecard_row(
    task_row: dict[str, Any],
    provider_spec: dict[str, Any],
    *,
    provider_role: str,
    artifact_dir: str,
) -> dict[str, Any]:
    planned = _planned_artifacts(artifact_dir, provider_role, task_row["task_id"])
    return {
        "schema": SCORECARD_SCHEMA,
        "task_set_id": task_row["task_set_id"],
        "task_id": task_row["task_id"],
        "benchmark_id": task_row["benchmark_id"],
        "coverage_unit": task_row["coverage_unit"],
        "provider_role": provider_role,
        "harness_id": provider_spec["harness_id"],
        "model_id": provider_spec["model_id"],
        "execution_mode": "manifest_only",
        "status": "planned",
        "failure_class": "not_executed",
        "raw_prompt_sha256": task_row["raw_prompt_sha256"],
        "raw_output_sha256": "",
        "raw_prompt_path": planned["prompt.txt"],
        "raw_output_path": planned["output.txt"],
        "receipt_path": planned["receipt.json"],
        "tool_trace_path": planned["tool_trace.json"],
        "metrics": {},
        "limitations": [
            "Manifest-only row; no provider, endpoint, harness, or benchmark was executed.",
            f"Adapter state: {provider_spec['adapter_state']}",
        ],
        "adapter_state": provider_spec["adapter_state"],
        "allowed_modes": provider_spec.get("allowed_modes", []),
        "required_receipts": provider_spec.get("required_receipts", []),
    }
def _planned_artifacts(artifact_dir: str, provider_role: str, task_id: str) -> dict[str, str]:
    base = Path(artifact_dir) / provider_role / task_id
    return {
        "prompt.txt": str(base / "prompt.txt"),
        "output.txt": str(base / "output.txt"),
        "tool_trace.json": str(base / "tool_trace.json"),
        "receipt.json": str(base / "receipt.json"),
        "metrics.json": str(base / "metrics.json"),
        "limitations.md": str(base / "limitations.md"),
    }
