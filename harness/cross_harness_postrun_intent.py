"""Pre-run intent matrix for cross-harness post-run validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "harness.cross-harness-postrun-intended-matrix/v1"
ROW_SCHEMA = "harness.cross-harness-task-scorecard/v1"

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _one(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get(field, "")) == value]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {field} row for {value}")
    return matches[0]

def build_intended_matrix(
    manifest: dict[str, Any], *, run_id: str, phase: str, task_ids: list[str],
    roles: list[str], repetitions: int, execution_mode: str, cache_state: str,
    source_commit: str, source_snapshot_sha256: str, row_schema: str = ROW_SCHEMA,
) -> dict[str, Any]:
    """Return the pre-run denominator that later validation must not reduce."""
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
        raise ValueError("repetitions must be positive")
    cells: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    specs = manifest.get("provider_specs", []) if isinstance(manifest.get("provider_specs"), list) else []
    task_set_id = str(manifest.get("task_set_id", ""))
    for role in roles:
        spec = _one(specs, "provider_role", role)
        for task_id in task_ids:
            for repetition in range(1, repetitions + 1):
                key = (task_set_id, task_id, repetition, role)
                if key in seen:
                    raise ValueError(f"duplicate intended cell: {key}")
                seen.add(key)
                cells.append({
                    "task_set_id": task_set_id, "task_id": task_id, "repetition": repetition,
                    "provider_role": role, "harness_id": str(spec.get("harness_id", "")),
                    "adapter_id": str(spec.get("adapter_id", "")), "model_id": str(spec.get("model_id", "")),
                    "requested_model_reference": str(spec.get("requested_model_reference", "")),
                })
    return {
        "schema": SCHEMA, "run_id": run_id, "phase": phase, "task_set_id": task_set_id,
        "task_ids": list(task_ids), "roles": list(roles), "repetitions": list(range(1, repetitions + 1)),
        "execution_mode": execution_mode, "cache_state": cache_state, "source_commit": source_commit,
        "source_snapshot_sha256": source_snapshot_sha256, "row_schema": row_schema, "cells": cells,
        "does_not_prove": [
            "The intent matrix records the pre-run denominator; it does not prove any provider executed.",
            "SHA-256 values here identify local bytes; they are not authenticity proof by themselves.",
        ],
    }

def write_intended_matrix(run_root: Path, matrix: dict[str, Any]) -> tuple[Path, str]:
    path = Path(run_root) / "intended-matrix.json"
    path.write_bytes(_canonical(matrix) + b"\n")
    return path, _sha_file(path)

def attach_intent_matrix(
    run_root: Path, manifest: dict[str, Any], plans: list[dict[str, Any]], *, run_id: str,
    phase: str, roles: list[str], repetitions: int, execution_mode: str, cache_state: str,
    source_commit: str, source_snapshot_sha256: str,
) -> tuple[Path, str]:
    task_ids = []
    for plan in plans:
        if plan["task_id"] not in task_ids:
            task_ids.append(plan["task_id"])
    path, digest = write_intended_matrix(run_root, build_intended_matrix(
        manifest, run_id=run_id, phase=phase, task_ids=task_ids, roles=roles,
        repetitions=repetitions, execution_mode=execution_mode, cache_state=cache_state,
        source_commit=source_commit, source_snapshot_sha256=source_snapshot_sha256))
    for plan in plans:
        plan["intended_matrix_sha256"] = digest
    return path, digest
