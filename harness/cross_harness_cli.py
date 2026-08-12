"""Packaged command for admitted cross-harness execution."""
from __future__ import annotations

import argparse, hashlib, json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapter_runtime_matrix import _endpoint_gate_result
from .cross_harness_adapters import DirectCodexAdapter, FlywheelRouterAdapter, LocalRouterAdapter
from .cross_harness_artifacts import canonical_sha256, recheck_attempt_receipt, write_artifact_index
from .cross_harness_executor import execute_cross_harness_manifest, resolve_task_ids


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in rows:
        if key in out: raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_pairs)
    if not isinstance(value, dict): raise ValueError(f"JSON object required: {path}")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _csv(value: str) -> list[str]: return [item.strip() for item in value.split(",") if item.strip()]


def _runtime(matrix: dict[str, Any], role: str) -> dict[str, Any]:
    rows = [row for row in matrix.get("runtime_rows", [])
            if isinstance(row, dict) and row.get("provider_role") == role]
    if len(rows) != 1: raise ValueError(f"expected exactly one runtime row for {role}")
    return rows[0]


def _block(row: dict[str, Any], code: str) -> None:
    row["blocking_gates"] = sorted(set(str(item) for item in row.get("blocking_gates", [])) | {code})
    row["focused_run_ready"] = False


def _apply_admission(matrix: dict[str, Any], path: Path, manifest: dict[str, Any],
                     selectors: list[str], roles: list[str], repetitions: int) -> None:
    """Independently recheck every admission attempt; a failed role stays local."""
    try: admission_sha = _sha(path)
    except OSError: admission_sha = ""
    matrix["admission_receipt_path"], matrix["admission_receipt_sha256"] = str(path), admission_sha
    try: admission = _load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        for role in roles: _block(_runtime(matrix, role), "admission_receipt_malformed")
        return
    if admission.get("schema") != "harness.cross-harness-run-receipt/v1":
        for role in roles: _block(_runtime(matrix, role), "admission_schema_mismatch")
        return
    if admission.get("phase") != "admission-smoke":
        for role in roles: _block(_runtime(matrix, role), "admission_phase_mismatch")
        return
    selected = resolve_task_ids(manifest.get("task_rows", []), selectors)
    rows = [row for row in admission.get("rows", []) if isinstance(row, dict)]
    if {str(row.get("provider_role", "")) for row in rows} != set(roles):
        for role in roles: _block(_runtime(matrix, role), "admission_selection_mismatch")
        return
    expected = {(task, repetition) for task in selected for repetition in range(1, repetitions + 1)}
    root = path.parent.resolve()
    for role in roles:
        runtime, role_rows = _runtime(matrix, role), [row for row in rows if row.get("provider_role") == role]
        actual = {(str(row.get("task_id", "")), row.get("repetition")) for row in role_rows}
        if actual != expected or len(role_rows) != len(expected) or any(row.get("phase") != "admission-smoke" for row in role_rows):
            _block(runtime, "admission_selection_mismatch"); continue
        failed = False
        for row in role_rows:
            try:
                receipt = Path(str(row.get("receipt_path", ""))).resolve(strict=True)
                if not receipt.is_relative_to(root) or recheck_attempt_receipt(receipt, row) != "verified":
                    failed = True; break
            except (OSError, ValueError): failed = True; break
            if row.get("primary_outcome") != "completed": failed = True; break
        if failed: _block(runtime, "admission_role_failed")


def _gate_receipt(row: dict[str, Any]) -> str:
    body = {key: value for key, value in row.items() if key not in {"receipt_hash", "latency_ms"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def _recheck_local_gate(matrix: dict[str, Any], path: Path, run_id: str, roles: list[str],
                        now: datetime, max_age: int) -> None:
    """Authenticate the exact bound gate before applying the existing freshness check."""
    try: actual_sha = _sha(path)
    except OSError: actual_sha = ""
    bound_sha = str(matrix.get("endpoint_gate_sha256", ""))
    matrix.update(endpoint_gate_path=str(path), endpoint_gate_sha256=actual_sha,
                  expected_gate_run_id=run_id, max_age_seconds=max_age)
    try: gate = _load(path)
    except (OSError, ValueError, json.JSONDecodeError): gate = {}
    global_code = ""
    if not actual_sha: global_code = "endpoint_gate_missing"
    elif actual_sha != bound_sha: global_code = "endpoint_gate_hash_mismatch"
    elif gate.get("schema") != "harness.model-endpoint-gate/v1": global_code = "endpoint_gate_schema_mismatch"
    elif gate.get("run_id") != run_id: global_code = "endpoint_gate_run_mismatch"
    gate_rows = gate.get("rows", []) if isinstance(gate.get("rows"), list) else []
    for role in roles:
        row = _runtime(matrix, role)
        if not role.startswith("local_"): continue
        profiles = row.get("endpoint_profile_matches", [])
        row["blocking_gates"] = [str(code) for code in row.get("blocking_gates", [])
                                 if not str(code).startswith("endpoint_gate")]
        code, matches = global_code, []
        if len(profiles) != 1 or not isinstance(profiles[0], dict): code = "endpoint_profile_ambiguous"
        elif not code:
            selected = [item for item in gate_rows if isinstance(item, dict)
                        and item.get("selected_profile_id") == profiles[0].get("profile_id")]
            if len(selected) != 1: code = "endpoint_gate_duplicate_profile" if selected else "endpoint_gate_profile_mismatch"
            elif selected[0].get("schema") != "harness.model-endpoint-gate.row/v1": code = "endpoint_gate_row_schema_mismatch"
            elif selected[0].get("receipt_hash") != _gate_receipt(selected[0]): code = "endpoint_gate_receipt_drift"
            else: matches, code = _endpoint_gate_result(profiles, gate, run_id, now, max_age)
        row["endpoint_gate_matches"], row["endpoint_gate_ready"] = matches, not code
        if code: _block(row, code)
        else: row["focused_run_ready"] = not row["blocking_gates"]


_PROFILE_FIELDS = {"profile_id", "model", "backend", "provider_role", "model_ref", "endpoint_url",
                   "root_exists", "supports_agentic_workflow", "live_probed"}


def _local_profiles(matrix: dict[str, Any], roles: list[str]) -> dict[str, dict[str, Any]]:
    local_roles = [role for role in roles if role.startswith("local_")]
    if not local_roles: return {}
    path = Path(str(matrix.get("endpoint_profiles_path", "")))
    try:
        artifact, actual = _load(path), _sha(path)
        rows = artifact.get("profiles", []) if isinstance(artifact.get("profiles"), list) else []
    except (OSError, ValueError, json.JSONDecodeError): actual, rows = "", []
    profiles = {}
    for role in local_roles:
        runtime, matches = _runtime(matrix, role), []
        projected = runtime.get("endpoint_profile_matches", [])
        if len(projected) == 1 and isinstance(projected[0], dict):
            wanted = projected[0]
            matches = [item for item in rows if isinstance(item, dict)
                       and item.get("profile_id") == wanted.get("profile_id")
                       and canonical_sha256(item) == wanted.get("profile_sha256")]
        if actual != matrix.get("endpoint_profiles_sha256"): _block(runtime, "endpoint_profile_artifact_hash_mismatch")
        elif len(matches) != 1: _block(runtime, "endpoint_profile_artifact_ambiguous")
        else:
            profile = {key: matches[0].get(key) for key in _PROFILE_FIELDS}
            profile["profile_sha256"] = canonical_sha256(matches[0]); profiles[role] = profile
    return profiles


def build_adapter_registry(matrix: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    selected = _local_profiles(matrix, roles); adapters = {}
    for role in roles:
        if role == "codex_harness": adapters[role] = DirectCodexAdapter()
        elif role == "flywheel_harness": adapters[role] = FlywheelRouterAdapter()
        elif role.startswith("local_"):
            fallback = {"profile_id": "", "backend": "", "model_ref": "", "endpoint_url": ""}
            adapters[role] = LocalRouterAdapter(role, selected.get(role, fallback))
        else: raise ValueError(f"unsupported execution role: {role}")
    return adapters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flywheel cross-harness-execute",
                                     description="Execute admitted cross-harness benchmark rows.")
    for flag in ("manifest", "runtime-matrix", "artifact-root", "roles", "source-commit",
                 "source-root", "phase", "run-id"):
        parser.add_argument(f"--{flag}", required=True)
    parser.add_argument("--tasks", "--task-selectors", dest="tasks", required=True)
    parser.add_argument("--cache", "--cache-state", dest="cache", required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--timeout", "--timeout-seconds", dest="timeout", type=int, required=True)
    parser.add_argument("--endpoint-gate", default="")
    parser.add_argument("--gate-run-id", default="")
    parser.add_argument("--admission-receipt", default="")
    parser.add_argument("--max-gate-age", "--max-gate-age-seconds", dest="max_gate_age", type=int, default=900)
    parser.add_argument("--strict-exit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest, matrix = _load(Path(args.manifest)), _load(Path(args.runtime_matrix))
    if manifest.get("schema") != "harness.cross-harness-manifest/v1": raise ValueError("manifest schema mismatch")
    if matrix.get("schema") != "harness.adapter-runtime-matrix/v1": raise ValueError("runtime matrix schema mismatch")
    roles, selectors = _csv(args.roles), _csv(args.tasks)
    if any(role.startswith("local_") for role in roles):
        if args.endpoint_gate and args.gate_run_id:
            _recheck_local_gate(matrix, Path(args.endpoint_gate), args.gate_run_id, roles,
                                datetime.now(UTC), args.max_gate_age)
        else:
            for role in roles:
                if role.startswith("local_"): _block(_runtime(matrix, role), "endpoint_gate_missing")
    if args.admission_receipt:
        _apply_admission(matrix, Path(args.admission_receipt), manifest, selectors, roles, args.repetitions)
    run = execute_cross_harness_manifest(manifest, matrix, build_adapter_registry(matrix, roles),
        artifact_root=Path(args.artifact_root), source_root=Path(args.source_root), run_id=args.run_id,
        phase=args.phase, selectors=selectors, roles=roles, repetitions=args.repetitions,
        cache_state=args.cache, timeout_seconds=args.timeout, source_commit=args.source_commit)
    run_root = Path(args.artifact_root) / args.run_id
    scorecard = run_root / "scorecard.json"
    scorecard.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": run["rows"]},
                         sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="")
    write_artifact_index(run_root, [path for path in run_root.rglob("*")
                                   if path.is_file() and path.name != "artifact-index.json"])
    print(json.dumps({"run_id": args.run_id, "run_path": str(run_root / "run.json"),
                      "scorecard_path": str(scorecard), "rows": len(run["rows"])}, sort_keys=True))
    failed = any(row.get("primary_outcome") != "completed" for row in run["rows"])
    return 1 if args.strict_exit and failed else 0


if __name__ == "__main__": raise SystemExit(main())
