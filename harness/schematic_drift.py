"""Metadata-only schematic drift checks for closed-loop integration docs."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
SCHEMA = "harness.schematic-drift-check/v1"

_REPO = Path(__file__).resolve().parent.parent
INTEGRATION_MAP_SCHEMA = "harness.cross-harness-integration-map/v1"
DEFAULT_REQUIRED_NODES = [
    "agentic_task_manifest_generator", "cross_harness_manifest",
    "adapter_runtime_matrix", "endpoint_gates", "forum_route_receipts",
    "mcp_tool_health", "embodied_realtime_plan", "benchmark_execution_matrix",
    "closed_loop_seed", "closed_loop_outcome", "benchmark_coverage",
    "harness_comparison", "cross_harness_executor", "objective_evidence_matrix",
]
DEFAULT_REQUIRED_EDGES = [
    ("agentic_task_manifest_generator", "benchmark_execution_matrix"),
    ("cross_harness_manifest", "benchmark_execution_matrix"),
    ("adapter_runtime_matrix", "benchmark_execution_matrix"),
    ("cross_harness_manifest", "cross_harness_executor"),
    ("adapter_runtime_matrix", "cross_harness_executor"),
    ("endpoint_gates", "cross_harness_executor"),
    ("cross_harness_executor", "benchmark_coverage"),
    ("cross_harness_executor", "harness_comparison"),
    ("cross_harness_executor", "closed_loop_seed"),
    ("forum_route_receipts", "closed_loop_seed"),
    ("mcp_tool_health", "closed_loop_seed"),
    ("embodied_realtime_plan", "benchmark_execution_matrix"),
    ("benchmark_execution_matrix", "closed_loop_seed"),
    ("closed_loop_seed", "closed_loop_outcome"),
]
DEFAULT_REQUIRED_FILES = {
    "agentic_task_manifest_generator": "scripts/run_agentic_task_set_manifest.py",
    "cross_harness_manifest": "scripts/run_cross_harness_manifest.py",
    "adapter_runtime_matrix": "scripts/run_adapter_runtime_matrix.py",
    "forum_route_receipts": "scripts/run_forum_route_receipts.py",
    "mcp_tool_health": "scripts/run_mcp_tool_health_receipts.py",
    "embodied_realtime_plan": "scripts/run_embodied_realtime_multimodal_plan.py",
    "benchmark_execution_matrix": "scripts/run_benchmark_execution_matrix.py",
    "closed_loop_seed": "scripts/run_closed_loop_benchmark_seed.py",
    "closed_loop_outcome": "scripts/run_closed_loop_outcome_report.py",
    "cross_harness_executor": "harness/cross_harness_executor.py",
    "cross_harness_integration_map": "scripts/run_cross_harness_integration_map.py",
}
STALE_PHRASES = [
    "next highest-leverage implementation step is still a non-executing manifest generator",
    "agentic task-set manifest command is not implemented yet",
]
def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))
def build_drift_report(
    graph: dict[str, Any],
    *,
    graph_path: str,
    report_text: str = "",
    report_path: str = "",
    required_nodes: list[str] | None = None,
    required_edges: list[tuple[str, str]] | None = None,
    required_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    required_nodes = required_nodes or list(DEFAULT_REQUIRED_NODES)
    required_edges = required_edges or list(DEFAULT_REQUIRED_EDGES)
    required_files = required_files or dict(DEFAULT_REQUIRED_FILES)
    observed_nodes = sorted({
        str(row.get("id", ""))
        for row in graph.get("nodes", [])
        if isinstance(row, dict) and row.get("id")
    })
    observed_edges = sorted({
        (str(row.get("from", "")), str(row.get("to", "")))
        for row in graph.get("edges", [])
        if isinstance(row, dict) and row.get("from") and row.get("to")
    })
    missing_nodes = sorted(set(required_nodes) - set(observed_nodes))
    missing_edges = sorted([
        {"from": source, "to": target}
        for source, target in required_edges
        if (source, target) not in set(observed_edges)
    ], key=lambda row: (row["from"], row["to"]))
    file_rows = [
        {
            "id": key,
            "path": path_text,
            "exists": (_REPO / path_text).exists(),
        }
        for key, path_text in sorted(required_files.items())
    ]
    missing_files = [row for row in file_rows if not row["exists"]]
    stale_phrases = [
        phrase
        for phrase in STALE_PHRASES
        if report_text and phrase.lower() in report_text.lower()
    ]
    report_input_errors = []
    if report_path:
        marker = f"Schema: `{INTEGRATION_MAP_SCHEMA}`"
        report_input_errors = ([] if marker in report_text else [
            "integration_map_schema_missing" if not report_text else "integration_map_schema_mismatch"
        ])
    drift = bool(missing_nodes or missing_edges or missing_files or stale_phrases or report_input_errors)
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "status": "drift_detected" if drift else "no_drift_detected",
        "verdict": "SCHEMATIC_DRIFT" if drift else "SCHEMATIC_CURRENT_UNVALIDATED",
        "graph_path": graph_path,
        "graph_schema": graph.get("schema", ""),
        "report_path": report_path,
        "observed_node_count": len(observed_nodes),
        "observed_edge_count": len(observed_edges),
        "required_nodes": required_nodes,
        "missing_nodes": missing_nodes,
        "required_edges": [{"from": source, "to": target} for source, target in required_edges],
        "missing_edges": missing_edges,
        "required_files": file_rows,
        "missing_files": missing_files,
        "stale_phrases": stale_phrases,
        "report_input_errors": report_input_errors,
        "non_execution_guards": [
            "Does not run tests.",
            "Does not run benchmarks.",
            "Does not call providers.",
            "Does not probe endpoints.",
            "Does not read model weights.",
        ],
        "summary": {
            "drift": drift,
            "missing_nodes": len(missing_nodes),
            "missing_edges": len(missing_edges),
            "missing_files": len(missing_files),
            "stale_phrases": len(stale_phrases),
            "report_input_errors": len(report_input_errors),
        },
    }
def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Schematic drift check",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Verdict: `{report['verdict']}`",
        f"- Graph: `{report['graph_path']}`",
        f"- Missing nodes: `{len(report['missing_nodes'])}`",
        f"- Missing edges: `{len(report['missing_edges'])}`",
        f"- Missing files: `{len(report['missing_files'])}`",
        f"- Stale phrases: `{len(report['stale_phrases'])}`",
        f"- Report input errors: `{len(report['report_input_errors'])}`",
        "",
    ]
    if report["missing_nodes"]:
        lines.extend(["## Missing nodes", ""])
        lines.extend(f"- `{node}`" for node in report["missing_nodes"])
        lines.append("")
    if report["missing_edges"]:
        lines.extend(["## Missing edges", ""])
        lines.extend(f"- `{row['from']} -> {row['to']}`" for row in report["missing_edges"])
        lines.append("")
    if report["missing_files"]:
        lines.extend(["## Missing files", ""])
        lines.extend(f"- `{row['id']}`: `{row['path']}`" for row in report["missing_files"])
        lines.append("")
    if report["stale_phrases"]:
        lines.extend(["## Stale phrases", ""])
        lines.extend(f"- `{phrase}`" for phrase in report["stale_phrases"])
        lines.append("")
    if report["report_input_errors"]:
        lines.extend(["## Report input errors", ""])
        lines.extend(f"- `{error}`" for error in report["report_input_errors"])
        lines.append("")
    lines.extend(["## Non-execution guards", ""])
    lines.extend(f"- {guard}" for guard in report.get("non_execution_guards", []))
    return "\n".join(lines) + "\n"
