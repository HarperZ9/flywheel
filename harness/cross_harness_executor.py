"""Typed cross-harness row expansion and execution."""
from __future__ import annotations

import hashlib, json
from pathlib import Path
from typing import Any
from harness.cross_harness_artifacts import (bind_attempt_receipt, canonical_sha256, create_attempt_workspace,
    materialize_response_envelope, preflight_artifact_root, recheck_attempt_receipt, remove_readonly_tree,
    snapshot_source_tree, validate_execution_components, write_artifact_index)
from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from harness.cross_harness_types import (AttemptRequest, metric_null_reasons, sanitize_evidence,
    validate_elapsed_ms)
class _MalformedAttempt(ValueError): pass

SHARED_TOOL_POLICY = {
    "version": "cross-harness-read-only/v1", "allow_read": True,
    "allow_write": False, "allow_exec": False, "allow_mcp": False,
    "max_steps": 6, "max_output_tokens": 2048,
}

def resolve_task_ids(task_rows: list[dict[str, Any]], selectors: list[str]) -> list[str]:
    task_ids = [str(row.get("task_id", "")) for row in task_rows]
    resolved: list[str] = []
    for selector in selectors:
        matches = [task_id for task_id in task_ids
                   if task_id == selector or task_id.startswith(f"{selector}-")]
        if not matches:
            raise ValueError(f"unknown task selector: {selector}")
        if len(matches) != 1:
            raise ValueError(f"ambiguous task selector: {selector}")
        if matches[0] not in resolved:
            resolved.append(matches[0])
    return resolved

def derive_primary_outcome(execution_state: str, oracle_state: str, receipt_state: str) -> tuple[str, str]:
    allowed = (
        {"not_started", "unavailable", "launched", "returned", "timeout", "malformed", "internal_error"},
        {"not_run", "pass", "fail", "unverifiable"},
        {"not_emitted", "verified", "drift"},
    )
    for name, value, values in zip(("execution", "oracle", "receipt"),
                                   (execution_state, oracle_state, receipt_state), allowed):
        if value not in values:
            raise ValueError(f"invalid {name} state: {value}")
    if execution_state in {"not_started", "launched"}:
        raise ValueError(f"execution state cannot be derived yet: {execution_state}")
    if execution_state == "returned" and receipt_state == "not_emitted":
        raise ValueError("inconsistent receipt state: returned attempt has no receipt")
    if execution_state in {"unavailable", "timeout", "internal_error", "malformed"}:
        outcome = execution_state
    elif receipt_state == "drift":
        outcome = "receipt_drift"
    elif oracle_state == "unverifiable":
        outcome = "unverifiable"
    elif oracle_state != "pass":
        outcome = "oracle_fail"
    else:
        outcome = "completed"
    status = ({"unavailable": "skipped", "receipt_drift": "invalid"}.get(outcome)
              or ("failed" if outcome in {"timeout", "malformed", "internal_error"} else "executed"))
    return outcome, status

def comparison_key(row: dict[str, Any]) -> str:
    fields = ("task_set_id", "task_id", "raw_prompt_sha256", "input_sha256s", "tool_policy_sha256",
              "model_id", "cache_state", "phase", "execution_mode", "source_snapshot_sha256",
              "workspace_snapshot_sha256")
    return canonical_sha256({field: row.get(field) for field in fields})

def _one(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get(field, "")) == value]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {field} row for {value}")
    return matches[0]


def _unavailable_evidence(role: str, runtime: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    profiles = runtime.get("endpoint_profile_matches", [])
    gates = runtime.get("endpoint_gate_matches", [])
    profile = profiles[0] if len(profiles) == 1 and isinstance(profiles[0], dict) else {}
    gate = gates[0] if len(gates) == 1 and isinstance(gates[0], dict) else {}
    blocking = [str(code) for code in runtime.get("blocking_gates", [])]
    return {
        "role": role, "backend": str(profile.get("backend", "")),
        "requested_model_reference": str(profile.get("model_ref", "")),
        "observed_model_reference": str(gate.get("observed_model_ref", "")),
        "endpoint_profile_id": str(profile.get("profile_id", "")),
        "endpoint_profile_sha256": str(profile.get("profile_sha256", "")),
        "attempted_gate_path": str(matrix.get("endpoint_gate_path", "")),
        "attempted_gate_sha256": str(matrix.get("endpoint_gate_sha256", "")),
        "attempted_gate_run_id": str(matrix.get("expected_gate_run_id", "")),
        "blocking_gates": blocking, "failure_reason": ",".join(blocking),
    }


def expand_attempt_rows(
    manifest: dict[str, Any], runtime_matrix: dict[str, Any], *, artifact_root: Path,
    run_id: str, phase: str, selectors: list[str], roles: list[str], repetitions: int,
) -> list[dict[str, Any]]:
    """Expand a manifest into deterministic planned rows without launching adapters."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    task_rows = manifest.get("task_rows", [])
    validate_execution_components(task_rows, run_id, phase, roles)
    selected = resolve_task_ids(task_rows, selectors)
    policy_hash, rows, seen = canonical_sha256(SHARED_TOOL_POLICY), [], set()
    for role in roles:
        spec = _one(manifest.get("provider_specs", []), "provider_role", role)
        runtime = _one(runtime_matrix.get("runtime_rows", []), "provider_role", role)
        for task_id in selected:
            task = _one(task_rows, "task_id", task_id)
            for repetition in range(1, repetitions + 1):
                key = (run_id, phase, role, task_id, repetition)
                if key in seen:
                    raise ValueError(f"duplicate attempt key: {key}")
                seen.add(key)
                attempt = Path(artifact_root) / run_id / phase / role / task_id / f"rep-{repetition:03d}"
                rows.append({
                    "attempt_key": list(key), "run_id": run_id, "phase": phase,
                    "provider_role": role, "harness_id": str(spec.get("harness_id", "")),
                    "adapter_id": str(spec.get("adapter_id", "")),
                    "model_id": str(spec.get("target_model", "")),
                    "task_set_id": str(manifest.get("task_set_id", "")), "task_id": task_id,
                    "benchmark_id": str(task.get("benchmark_id", "")), "coverage_unit": str(task.get("coverage_unit", "")),
                    "task": task, "repetition": repetition, "attempt_dir": str(attempt),
                    "execution_mode": "focused_run", "tool_policy": dict(SHARED_TOOL_POLICY),
                    "tool_policy_sha256": policy_hash,
                    "planned_available": runtime.get("focused_run_ready") is True,
                    "runtime_evidence": _unavailable_evidence(role, runtime, runtime_matrix),
                })
    return rows


def _write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8", newline="")
    return path


def _seal_row(row: dict[str, Any], files: dict[str, Path], attempt: Path) -> Path:
    metrics = attempt / "metrics.json"; _write_json(metrics, row["metrics"]); files[metrics.name] = metrics
    limits = attempt / "limitations.md"; limits.write_text("\n".join(f"- {item}" for item in row["limitations"]) + "\n", encoding="utf-8"); files[limits.name] = limits
    receipt_path = attempt / "receipt.json"; row["receipt_path"] = str(receipt_path)
    row["receipt_state"] = "verified"
    row["orthogonal_states"] = {axis: row[axis] for axis in ("execution_state", "oracle_state", "receipt_state")}
    row["primary_outcome"], row["status"] = derive_primary_outcome(*row["orthogonal_states"].values())
    receipt = bind_attempt_receipt(row, files, receipt_path)
    row["receipt_subject_sha256"] = receipt["receipt_subject_sha256"]
    row["receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    row["receipt_does_not_bind"] = receipt["does_not_bind"]
    row["receipt_state"] = recheck_attempt_receipt(receipt_path, row)
    row["orthogonal_states"]["receipt_state"] = row["receipt_state"]
    row["primary_outcome"], row["status"] = derive_primary_outcome(*row["orthogonal_states"].values())
    return receipt_path


def execute_cross_harness_manifest(
    manifest: dict[str, Any], runtime_matrix: dict[str, Any], adapters: dict[str, Any], *,
    artifact_root: Path, source_root: Path, run_id: str, phase: str, selectors: list[str],
    roles: list[str], repetitions: int, cache_state: str = "cold_declared", timeout_seconds: int = 300,
    source_commit: str = "unverified",
) -> dict[str, Any]:
    """Execute every planned row while preserving unavailable and failed evidence."""
    source = Path(source_root).resolve(strict=True)
    validate_execution_components(manifest.get("task_rows", []), run_id, phase, roles)
    root = preflight_artifact_root(source, Path(artifact_root)); root.mkdir(parents=True, exist_ok=True)
    root = preflight_artifact_root(source, root)
    run_root = root / run_id; run_root.mkdir()
    before, after, rows, indexed, clean = snapshot_source_tree(source), None, [], [], []
    try:
        plans = expand_attempt_rows(manifest, runtime_matrix, artifact_root=root, run_id=run_id,
                                    phase=phase, selectors=selectors, roles=roles, repetitions=repetitions)
        for plan in plans:
            task, attempt = plan["task"], Path(plan["attempt_dir"])
            files: dict[str, Path] = {}; workspace_before = None
            row = {key: value for key, value in plan.items() if key not in {"task", "tool_policy", "planned_available"}}
            row.update({"schema": "harness.cross-harness-task-scorecard/v1", "cache_state": cache_state,
                        "source_commit": source_commit,
                        "source_snapshot_sha256": before["sha256"], "input_sha256s": dict(task.get("input_sha256s", {})),
                        "execution_state": "not_started", "oracle_state": "not_run", "receipt_state": "not_emitted",
                        "raw_prompt_sha256": str(task.get("raw_prompt_sha256", "")), "raw_output_sha256": "",
                        "raw_output_path": "", "tool_trace_path": "", "failure_class": "", "failure_detail": "",
                        "metrics": {}, "limitations": ["Actual enforcement is not assumed equivalent across adapters."],
                        "policy_equivalence": "non_equivalent", "availability_evidence": dict(plan["runtime_evidence"]),
                        "planned": True, "admitted": False, "launched": False, "blocked": False})
            try:
                try: workspace, observed = create_attempt_workspace(source, list(task.get("required_inputs", [])), dict(task.get("input_sha256s", {})), attempt)
                except ValueError as exc: raise _MalformedAttempt(str(exc)) from exc
                workspace_snapshot = snapshot_source_tree(workspace)
                workspace_before = workspace_snapshot
                workspace_before_path = attempt / "workspace-before.json"; _write_json(workspace_before_path, workspace_before); files[workspace_before_path.name] = workspace_before_path
                row.update(workspace_root=str(workspace), workspace_snapshot_sha256=workspace_snapshot["sha256"],
                           input_sha256s=observed, workspace_state="verified")
                prompt = attempt / "prompt.txt"; prompt.write_text(str(task.get("raw_prompt", "")), encoding="utf-8", newline=""); files[prompt.name] = prompt
                row["raw_prompt_path"] = str(prompt)
                request = AttemptRequest(run_id, phase, row["task_set_id"], row["task_id"], task.get("raw_prompt", ""),
                    row["raw_prompt_sha256"], row["provider_role"], row["harness_id"], row["adapter_id"], row["model_id"],
                    workspace, workspace_snapshot["sha256"], observed, dict(SHARED_TOOL_POLICY), row["tool_policy_sha256"],
                    row["repetition"], cache_state, timeout_seconds, attempt)
                adapter = adapters.get(row["provider_role"])
                if adapter is None or adapter.role != row["provider_role"] or adapter.adapter_id != row["adapter_id"]:
                    raise RuntimeError("adapter role or id mismatch")
                enforcement = adapter.enforcement(request)
                if sanitize_evidence(enforcement.description) != enforcement.description:
                    raise RuntimeError("secret-shaped enforcement evidence")
                actual_hash = canonical_sha256(enforcement.description)
                row.update(enforcement_description=enforcement.description, enforcement_sha256=actual_hash,
                           adapter_verification_claim=sanitize_evidence(enforcement.verification_state),
                           enforcement_verification_state="unverified")
                enforcement_path = attempt / "enforcement.json"; _write_json(enforcement_path, enforcement.description); files[enforcement_path.name] = enforcement_path
                if enforcement.description_sha256 != actual_hash: raise RuntimeError("adapter enforcement hash mismatch")
                if not plan["planned_available"]:
                    row.update(execution_state="unavailable", failure_class="runtime_unavailable",
                               failure_detail=row["availability_evidence"]["failure_reason"])
                else:
                    availability = adapter.availability(request)
                    row["availability_evidence"]["adapter_evidence"] = sanitize_evidence(availability.evidence)
                    row["availability_evidence"]["adapter_detail"] = sanitize_evidence(availability.detail)
                    if not availability.available:
                        row.update(execution_state="unavailable", failure_class=sanitize_evidence(availability.failure_class),
                                   failure_detail=sanitize_evidence(availability.detail))
                    else:
                        row.update(execution_state="launched", admitted=True, launched=True)
                        try: result = adapter.execute(request)
                        except TimeoutError as exc:
                            row.update(execution_state="timeout", failure_class="timeout", failure_detail=sanitize_evidence(str(exc))); result = None
                        if result is not None:
                            if result.execution_state not in {"returned", "timeout", "malformed", "internal_error", "unavailable"}:
                                raise RuntimeError(f"invalid adapter execution state: {result.execution_state}")
                            if result.output_text:
                                raw = attempt / "output.txt"; raw.write_text(result.output_text, encoding="utf-8", newline=""); files[raw.name] = raw
                                row.update(raw_output_path=str(raw), raw_output_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
                            elapsed_ms = validate_elapsed_ms(result.elapsed_ms)
                            metadata = sanitize_evidence({"usage": result.usage, "resource": result.resource_observation,
                                "capabilities": result.observed_capabilities, "violations": result.policy_violations,
                                "tool_trace": result.tool_trace, "model": result.model_observed,
                                "randomness": result.randomness_control, "failure_detail": result.failure_detail})
                            row.update(execution_state=result.execution_state, failure_class=sanitize_evidence(result.failure_class),
                                       failure_detail=metadata["failure_detail"],
                                       metrics={"latency_ms": elapsed_ms, "usage": metadata["usage"], "resource_observation": metadata["resource"]},
                                       model_observed=metadata["model"], randomness_control=metadata["randomness"],
                                       observed_capabilities=metadata["capabilities"], policy_violations=metadata["violations"])
                            trace = attempt / "tool_trace.json"; _write_json(trace, metadata["tool_trace"]); files[trace.name] = trace; row["tool_trace_path"] = str(trace)
                            if result.execution_state == "returned":
                                try: raw, artifacts = materialize_response_envelope(result.output_text, list(task.get("expected_artifacts", [])), attempt)
                                except ValueError as exc: raise _MalformedAttempt(str(exc)) from exc
                                files.update(artifacts); row.update(raw_output_path=str(raw), raw_output_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
                                provider_receipt = attempt / "provider-receipt.json"; _write_json(provider_receipt, {"model_observed": row["model_observed"], "elapsed_ms": elapsed_ms}); files[provider_receipt.name] = provider_receipt
                                core = {"workspace_root": str(workspace), "attempt_dir": str(attempt),
                                        "raw_prompt_sha256": row["raw_prompt_sha256"], "tool_policy_sha256": row["tool_policy_sha256"],
                                        "raw_artifact_sha256": row["raw_output_sha256"], "receipt_sha256": hashlib.sha256(provider_receipt.read_bytes()).hexdigest(),
                                        "orthogonal_states": {"execution_state": "returned", "oracle_state": "not_run", "receipt_state": "not_emitted"}}
                                oracle = evaluate_task_oracle(OracleContext(row["task_id"], dict(task.get("oracle", {})), raw, artifacts, observed, core))
                                row["oracle_evidence"] = {"reported_state": oracle.state, "checker_id": oracle.checker_id,
                                    "checker_version": oracle.checker_version, "evidence": oracle.evidence,
                                    "failure_codes": oracle.failure_codes, "checked_artifacts": oracle.checked_artifacts}
                                if oracle.state == "malformed": row.update(execution_state="malformed", oracle_state="not_run", failure_class="oracle_malformed", failure_detail=",".join(oracle.failure_codes))
                                else: row["oracle_state"] = oracle.state
                availability_path = attempt / "availability.json"; _write_json(availability_path, row["availability_evidence"]); files[availability_path.name] = availability_path
            except Exception as exc:
                if row["execution_state"] not in {"timeout", "malformed"}: row["execution_state"] = "malformed" if isinstance(exc, _MalformedAttempt) else "internal_error"
                row.update(oracle_state="not_run", failure_class=row["failure_class"] or type(exc).__name__,
                           failure_detail=sanitize_evidence(row["failure_detail"] or str(exc)))
                attempt.mkdir(parents=True, exist_ok=True)
            if workspace_before is not None:
                try:
                    workspace_after = snapshot_source_tree(Path(row["workspace_root"]))
                    snapshot_failed = False
                except Exception as exc:
                    workspace_after = {"schema": "harness.cross-harness-workspace-after/v1",
                                       "state": "snapshot_error", "error_type": type(exc).__name__}
                    snapshot_failed = True
                workspace_after_path = attempt / "workspace-after.json"
                _write_json(workspace_after_path, workspace_after); files[workspace_after_path.name] = workspace_after_path
                row["workspace_snapshot_after_sha256"] = workspace_after.get("sha256", canonical_sha256(workspace_after))
                if snapshot_failed or workspace_after != workspace_before:
                    row.update(execution_state="malformed", oracle_state="not_run", workspace_state="drift",
                               failure_class="workspace_drift", failure_detail="workspace changed during adapter attempt")
                    row["policy_violations"] = sorted(set(row.get("policy_violations", [])) | {"workspace_drift"})
            row["blocked"] = row["execution_state"] == "unavailable"
            row["metric_null_reasons"] = metric_null_reasons(row["metrics"])
            raw_path = attempt / "output.txt"
            if raw_path.is_file() and raw_path not in files.values(): files[raw_path.name] = raw_path; row.update(raw_output_path=str(raw_path), raw_output_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest())
            row["comparison_key"] = comparison_key(row)
            oracle_path = attempt / "oracle.json"; _write_json(oracle_path, row.get("oracle_evidence", {"reported_state": "not_run", "failure_codes": []})); files[oracle_path.name] = oracle_path
            resource_path = attempt / "resource.json"; _write_json(resource_path, row.get("metrics", {})); files[resource_path.name] = resource_path
            try: receipt = _seal_row(row, files, attempt)
            except Exception as exc: raise RuntimeError(f"attempt_receipt_seal_failed:{row['attempt_key']}") from exc
            files[receipt.name] = receipt
            rows.append(row); indexed.extend(files.values())
            if row["primary_outcome"] == "completed": clean.append(Path(row["workspace_root"]))
    finally:
        after = snapshot_source_tree(source)
    if before != after: raise RuntimeError("source_tree_changed")
    for workspace in clean: remove_readonly_tree(workspace)
    run = {"schema": "harness.cross-harness-run-receipt/v1", "run_id": run_id, "phase": phase,
           "rows": rows, "source_snapshot_before": before, "source_snapshot_after": after}
    comparison = run_root / "comparison-input.json"; _write_json(comparison, {"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows})
    run_path = run_root / "run.json"; _write_json(run_path, run); indexed.extend((comparison, run_path))
    write_artifact_index(run_root, indexed)
    return run
