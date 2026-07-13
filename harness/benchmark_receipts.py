"""Helpers for writing benchmark outputs into the local receipt store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.file_backed_store import FileBackedHarnessStore


def infer_benchmark_verdict(body: dict[str, Any]) -> str:
    """Infer a receipt verdict without pretending matrices are all-pass gates."""
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    witness_gate = summary.get("witness_gate") if isinstance(summary.get("witness_gate"), dict) else {}
    if "passed" in witness_gate:
        return "BENCHMARK_GATE_PASS" if witness_gate.get("passed") else "BENCHMARK_GATE_FAIL"
    if isinstance(body.get("passed"), bool):
        return "BENCHMARK_PASS" if body["passed"] else "BENCHMARK_FAIL"
    if summary:
        failed = int(summary.get("failed_rows", 0) or 0)
        skipped = int(summary.get("skipped_rows", 0) or 0)
        return "BENCHMARK_PARTIAL" if failed or skipped else "BENCHMARK_RECORDED"
    return "BENCHMARK_RECORDED"


def store_benchmark_outputs(
    body: dict[str, Any],
    *,
    store_root: str,
    kind: str,
    run_id: str = "",
    verdict: str = "",
    artifact_paths: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Store a benchmark body receipt and optional artifacts.

    `artifact_paths` contains `(path, label)` pairs. Missing paths are ignored so
    callers can pass optional Markdown outputs without extra branching.
    """
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs: list[dict[str, Any]] = [
        store.put_receipt(
            kind=kind,
            body=body,
            run_id=run_id,
            verdict=verdict or infer_benchmark_verdict(body),
        )
    ]
    for path_text, label in artifact_paths or []:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs
