"""Opt-in M7 routing collection helpers for retrospective M7 diagnostics."""
from __future__ import annotations
import json, subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def canonical_sha256(obj: Any) -> str:
    return sha256(canonical_json(obj).encode("utf-8")).hexdigest()
def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
def file_tree_sha256(root: Path) -> str | None:
    if not root.exists() or not root.is_dir():
        return None
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)})
    return canonical_sha256(rows)
def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
def ns_to_ms(ns: int | None) -> float | None:
    return None if ns is None else round(ns / 1_000_000, 3)
def task_identity(task) -> dict[str, Any]:
    workdir = Path(task.workdir)
    task_json = workdir.parent / "task.json"
    prompt_hash = text_sha256(task.prompt)
    oracle_cmd_hash = text_sha256(task.oracle_cmd)
    identity = {
        "task_id": task.task_id,
        "prompt_sha256": prompt_hash,
        "system_sha256": text_sha256(task.system or ""),
        "oracle": task.oracle,
        "oracle_cmd_sha256": oracle_cmd_hash,
        "held_out_cmd_sha256": text_sha256(getattr(task, "held_out_cmd", "") or ""),
        "candidate_path": task.candidate_path,
        "max_new_tokens": task.max_new_tokens,
        "seed": task.seed,
        "task_json_sha256": file_sha256(task_json),
        "oracle_files_sha256": file_tree_sha256(workdir / "tests"),
    }
    identity["task_source_sha256"] = canonical_sha256(identity)
    return identity
def _usage_block(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {"source": "not_returned", "tokens": None}
    return {"source": "provider_reported", "tokens": usage}
def _oracle_receipt(oracle_result) -> dict[str, Any]:
    stdout = getattr(oracle_result, "stdout_excerpt", "") or ""
    return {
        "oracle_type": "pytest",
        "cmd": getattr(oracle_result, "cmd", ""),
        "cmd_sha256": text_sha256(getattr(oracle_result, "cmd", "") or ""),
        "output_hash": getattr(oracle_result, "output_hash", ""),
        "rc": getattr(oracle_result, "rc", None),
        "verdict": oracle_result.verdict(),
        "execution": getattr(getattr(oracle_result, "execution", ""), "value", getattr(oracle_result, "execution", "")),
        "attribution": getattr(getattr(oracle_result, "attribution", ""), "value", getattr(oracle_result, "attribution", "")),
        "stdout_excerpt_sha256": text_sha256(stdout),
        "raw_stdout_sha256": getattr(oracle_result, "raw_stdout_sha256", "") or None,
        "duration_ns": getattr(oracle_result, "duration_ns", 0) or None,
    }
def candidate_row(*, candidate_index: int, text: str, model_ref_requested: str,
                  model_ref_observed: str, served_model: str = "", seed: int,
                  temperature: float, prompt_hash_provider: str, usage: Any,
                  cache: str, oracle_result, generation_duration_ns: int | None,
                  oracle_duration_ns: int | None) -> dict[str, Any]:
    identity_status = (
        "reported_unverified"
        if model_ref_observed or served_model
        else "requested_unverified"
    )
    return {
        "candidate_index": candidate_index,
        "seed": seed,
        "temperature": temperature,
        "prompt_hash_provider": prompt_hash_provider,
        "completion_sha256": text_sha256(text),
        "completion_hash_scope": "post_extract_candidate_text",
        "model_ref_requested": model_ref_requested,
        "model_ref_observed": model_ref_observed,
        "served_model": served_model,
        "model_digest": None,
        "model_digest_status": "digest_not_returned",
        "model_identity_status": identity_status,
        "cache": cache,
        "usage": _usage_block(usage),
        "server_timing_ms": None,
        "cost": None,
        "generation_latency_ms": ns_to_ms(generation_duration_ns),
        "oracle_latency_ms": ns_to_ms(oracle_duration_ns),
        "candidate_total_latency_ms": (
            ns_to_ms(generation_duration_ns + oracle_duration_ns)
            if generation_duration_ns is not None and oracle_duration_ns is not None else None),
        "oracle_receipt": _oracle_receipt(oracle_result),
    }
def build_builtin_split_plan(*, tier: str, task_ids: list[str],
                             split_id: str) -> dict[str, Any]:
    tasks = []
    for index, task_id in enumerate(task_ids):
        bucket = int(sha256(f"{split_id}:{task_id}".encode("utf-8")).hexdigest()[:8], 16) % 100
        tasks.append({
            "task_id": task_id,
            "task_index": index,
            "bucket": bucket,
            "role": "retrospective_diagnostic",
            "freshness": "historical_visible",
        })
    return {
        "schema": "m7-routing-split-plan/v1",
        "split_id": split_id,
        "tier": tier,
        "task_family": f"m7_builtin_{tier}",
        "split_family": "retrospective_diagnostic",
        "assignment_policy": (
            "built-in M7 tasks are fixed retrospective diagnostics; bucket is "
            "stable audit metadata and not a train/calibration/final-holdout split"),
        "plan_written_before_generation": True,
        "ordering_proof_only": True,
        "fresh_task_family_manifest": None,
        "future_fresh_task_family_status": "unavailable_in_builtin_m7_path",
        "does_not_prove": [
            "split-plan hash proves implementation ordering only",
            "does not prove independent preregistration",
            "does not prove tasks were untouched by previous release analysis",
        ],
        "tasks": tasks,
    }
def _report_details(report: Any) -> list[dict[str, Any]]:
    if isinstance(report, dict):
        return list(report.get("per_task_detail") or [])
    return list(getattr(report, "per_task_detail", []) or [])
def _split_assignments(split_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for row in split_plan.get("tasks", []):
        task_id = str(row.get("task_id", ""))
        if not task_id:
            raise ValueError("routing split plan row missing task_id")
        if task_id in assignments:
            raise ValueError(f"duplicate routing split plan task_id: {task_id}")
        assignments[task_id] = row
    return assignments
def _resolved_key(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False)).casefold()
def _guard_distinct_outputs(*, scorecard: str, collection: str, split_plan: str) -> None:
    seen: dict[str, str] = {}
    for name, path in [("scorecard", scorecard), ("collection", collection),
                       ("split-plan", split_plan)]:
        if not path:
            continue
        key = _resolved_key(path)
        if key in seen:
            raise ValueError(f"routing {name} output collides with {seen[key]} output: {path}")
        seen[key] = name
def _arm_rows(arm_name: str, report: Any, assignments: dict[str, dict[str, Any]]
              ) -> list[dict[str, Any]]:
    expected, seen, rows = set(assignments), set(), []
    details = _report_details(report)
    if not details:
        raise ValueError(f"routing report arm {arm_name} has no per_task_detail")
    for detail in details:
        row = dict(detail)
        if str(row.get("arm_name", arm_name)) != arm_name:
            raise ValueError(f"routing report arm_name mismatch: {row.get('arm_name')} in {arm_name}")
        row["arm_name"] = arm_name
        task_id = str(row.get("task_id", ""))
        if task_id not in assignments:
            raise ValueError(f"routing split plan missing task_id: {task_id}")
        if task_id in seen:
            raise ValueError(f"duplicate routing report task_id for {arm_name}: {task_id}")
        seen.add(task_id); row["split_assignment"] = assignments[task_id]; rows.append(row)
    missing = sorted(expected - seen)
    if missing:
        raise ValueError(f"routing report arm {arm_name} missing task_id(s): {', '.join(missing)}")
    return rows
def measurement_denominators() -> dict[str, str]:
    return {
        "timer": "time.perf_counter_ns in runner process",
        "latency_unit": "milliseconds",
        "generation_latency_ms": (
            "time.perf_counter_ns around proposer.generate; includes Python/client/"
            "HTTP overhead and endpoint generation when a live endpoint is used"),
        "oracle_latency_ms": (
            "time.perf_counter_ns around oracle.verify; includes candidate file "
            "write, bytecode cleanup, pytest subprocess, and cleanup"),
        "candidate_total_latency_ms": "generation_latency_ms plus oracle_latency_ms",
        "task_arm_total_latency_ms": "time.perf_counter_ns around complete arm execution",
    }
def build_collection_artifact(*, run_id: str, tier: str, source_commit: str,
                              split_plan: dict[str, Any], split_plan_sha256: str,
                              split_plan_path: str, reports: dict[str, Any]) -> dict[str, Any]:
    assignments = _split_assignments(split_plan)
    rows: list[dict[str, Any]] = []
    if not reports:
        raise ValueError("routing collection requires at least one report arm")
    for arm_name, report in reports.items():
        rows.extend(_arm_rows(arm_name, report, assignments))
    return {
        "schema": "m7-routing-collection/v1",
        "created_utc": utc_now(),
        "run_id": run_id,
        "source_commit": source_commit,
        "tier": tier,
        "split_plan": {
            "path": split_plan_path,
            "sha256": split_plan_sha256,
            "scope": "ordering_only",
        },
        "measurement_denominators": measurement_denominators(),
        "unavailable_metric_policy": (
            "null plus explicit provenance; no inferred zero for server-only time, "
            "cost, model digest, or tokens not returned by the provider"),
        "rows": rows,
    }
def write_json_with_hash(path: str | Path, obj: Any) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    return file_sha256(p) or ""
def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, timeout=10
        ).strip()
    except Exception:
        return ""
def prepare_m7_collection(args: Any, *, tier: str, task_set: list[Any]) -> dict[str, Any]:
    enabled = bool(getattr(args, "routing_collection_out", ""))
    if getattr(args, "routing_split_plan_out", "") and not enabled:
        raise ValueError("--routing-split-plan-out requires --routing-collection-out")
    if not enabled:
        return {"enabled": False}
    out = Path(getattr(args, "routing_collection_out"))
    split_path = Path(getattr(args, "routing_split_plan_out", "") or out.with_suffix(".split-plan.json"))
    _guard_distinct_outputs(scorecard=getattr(args, "out", ""),
                            collection=str(out), split_plan=str(split_path))
    split_id = (
        getattr(args, "routing_split_id", "")
        or getattr(args, "run_id", "")
        or f"m7-builtin-{tier}-{Path(getattr(args, 'out')).stem}"
    )
    plan = build_builtin_split_plan(
        tier=tier, task_ids=[task.task_id for task in task_set], split_id=split_id)
    return {
        "enabled": True,
        "collection_path": str(out),
        "split_plan_path": str(split_path),
        "split_plan": plan,
        "split_plan_sha256": write_json_with_hash(split_path, plan),
    }
def finalize_m7_collection(state: dict[str, Any], *, reports: dict[str, Any],
                            meta: dict[str, Any], artifact_paths: list[tuple[str, str]],
                            tier: str, run_id: str, repo_root: Path) -> None:
    if not state.get("enabled"):
        return
    if _resolved_key(state["collection_path"]) == _resolved_key(state["split_plan_path"]):
        raise ValueError("routing collection output collides with split-plan output")
    collection = build_collection_artifact(
        run_id=run_id,
        tier=tier,
        source_commit=_git_head(repo_root),
        split_plan=state["split_plan"],
        split_plan_sha256=state["split_plan_sha256"],
        split_plan_path=state["split_plan_path"],
        reports=reports,
    )
    collection_sha = write_json_with_hash(state["collection_path"], collection)
    meta["routing_split_plan"] = {
        "schema": state["split_plan"]["schema"],
        "path": state["split_plan_path"],
        "sha256": state["split_plan_sha256"],
        "split_family": "retrospective_diagnostic",
        "scope": "ordering_only",
    }
    meta["routing_collection"] = {
        "schema": collection["schema"],
        "path": state["collection_path"],
        "sha256": collection_sha,
    }
    artifact_paths.extend([
        (state["collection_path"], "m7-routing-collection-json"),
        (state["split_plan_path"], "m7-routing-split-plan-json"),
    ])
