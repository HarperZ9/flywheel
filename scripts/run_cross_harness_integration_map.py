"""Map generated cross-harness artifacts without inferring runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.cross_harness_types import MODEL_IDENTITY_FIELDS, project_model_identity  # noqa: E402


SCHEMA = "harness.cross-harness-integration-map/v1"
GRAPH_SCHEMA = "harness.closed-loop-integration-graph/v1"
EXPECTED_SCHEMAS = {
    "lane_before": "flywheel.lanes/v1",
    "lane_after": "flywheel.lanes/v1",
    "auth": "harness.endpoint-auth-status/v1",
    "endpoint_profiles": "harness.model-endpoint-profiles/v1",
    "endpoint_gate": "harness.model-endpoint-gate/v1",
    "runtime_matrix": "harness.adapter-runtime-matrix/v1",
    "seed": "harness.closed-loop-benchmark-seed/v1",
    "coverage": "harness.benchmark-profile-coverage/v1",
    "comparison": "harness.comparison-report/v1",
    "outcome": "harness.closed-loop-outcome/v1",
}
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAPH = ROOT / "project-docs" / "schematics" / "closed-loop-integration.graph.json"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_object(path: Path, artifact_id: str) -> tuple[dict[str, Any], str, str | None]:
    if not path.is_file():
        return {}, f"{artifact_id}_missing", None
    try:
        raw = path.read_bytes()
    except OSError:
        return {}, f"{artifact_id}_unreadable", None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        body = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return {}, f"{artifact_id}_unreadable", digest
    if not isinstance(body, dict):
        return {}, f"{artifact_id}_not_object", digest
    return body, "", digest


def _observed_metadata(value: Any, pointer: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            if key in {"schema", "status", "verdict"} and isinstance(child, (str, bool, int, float)):
                rows.append({"pointer": child_pointer, "field": key, "value": str(child)})
            rows.extend(_observed_metadata(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_observed_metadata(child, f"{pointer}/{index}"))
    return rows


def _classification(value: str) -> str:
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    blocked = ("fail", "blocked", "unavailable", "missing", "stale", "drift", "timeout", "error")
    unknown = ("unknown", "unverifiable", "unvalidated", "insufficient", "partial", "not_run", "not_executed")
    if any(token in normalized for token in blocked):
        return "blocked"
    if any(token in normalized for token in unknown):
        return "unknown"
    return "observed"


def _model_identities(value: Any, source_schema: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(value, dict):
        source_schema = str(value.get("schema") or source_schema)
        if "target_model" in value or any(field in value for field in MODEL_IDENTITY_FIELDS):
            rows.append(project_model_identity(value, source_schema=source_schema))
        for child in value.values(): rows.extend(_model_identities(child, source_schema))
    elif isinstance(value, list):
        for child in value: rows.extend(_model_identities(child, source_schema))
    unique = {json.dumps(row, sort_keys=True): row for row in rows}
    return list(unique.values())


def build_integration_map(
    *, graph_path: str | Path, artifact_paths: dict[str, str | Path]
) -> dict[str, Any]:
    graph_file = Path(graph_path)
    graph, graph_error, graph_sha256 = _read_object(graph_file, "graph")
    graph_schema = graph.get("schema") if graph else None
    if not graph_error and graph_schema != GRAPH_SCHEMA:
        graph_error = "graph_schema_mismatch"
    artifacts = []
    evidence: dict[str, list[dict[str, str]]] = {
        "observed": [], "inferred": [], "blocked": [], "unknown": []
    }
    for item in _observed_metadata(graph):
        if item["field"] in {"status", "verdict"} and item["pointer"].startswith("/nodes/"):
            evidence["inferred"].append({
                "artifact_id": "graph", **item, "scope": "static_graph_declaration"
            })
    if graph_error:
        evidence["blocked"].append({
            "artifact_id": "graph", "field": "input_state", "pointer": "",
            "value": graph_error,
        })
    for artifact_id, expected_schema in EXPECTED_SCHEMAS.items():
        path_text = artifact_paths.get(artifact_id)
        path = Path(path_text) if path_text else None
        body, input_error, artifact_sha256 = (
            _read_object(path, artifact_id) if path else ({}, f"{artifact_id}_missing", None)
        )
        observed_schema = body.get("schema") if body else None
        if not input_error and observed_schema != expected_schema:
            input_error = f"{artifact_id}_schema_mismatch"
        metadata = _observed_metadata(body)
        artifact = {
            "id": artifact_id,
            "path": str(path) if path else None,
            "sha256": artifact_sha256,
            "expected_schema": expected_schema,
            "schema": observed_schema,
            "status": body.get("status") if body else None,
            "verdict": body.get("verdict") if body else None,
            "input_state": "blocked" if input_error else "observed",
            "blocking_reason": input_error or None,
            "observed_metadata": metadata,
            "model_identities": _model_identities(body),
        }
        artifacts.append(artifact)
        if input_error:
            evidence["blocked"].append({
                "artifact_id": artifact_id, "field": "input_state", "pointer": "",
                "value": input_error,
            })
        else:
            evidence["observed"].append({
                "artifact_id": artifact_id, "field": "schema", "pointer": "/schema",
                "value": str(observed_schema),
            })
            if body.get("status") is None and body.get("verdict") is None:
                evidence["unknown"].append({
                    "artifact_id": artifact_id, "field": "status", "pointer": "",
                    "value": "status_or_verdict_absent",
                })
        if input_error:
            continue
        for item in metadata:
            if item["field"] not in {"status", "verdict"}:
                continue
            bucket = _classification(item["value"])
            evidence[bucket].append({"artifact_id": artifact_id, **item})

    blocked_inputs = int(bool(graph_error)) + sum(
        row["input_state"] == "blocked" for row in artifacts
    )
    return {
        "schema": SCHEMA,
        "timestamp_utc": _now_utc(),
        "status": "blocked_inputs" if blocked_inputs else "runtime_artifacts_mapped",
        "graph": {
            "path": str(graph_file),
            "schema": graph_schema,
            "expected_schema": GRAPH_SCHEMA,
            "sha256": graph_sha256,
            "input_state": "blocked" if graph_error else "observed",
            "blocking_reason": graph_error or None,
            "evidence_scope": "static_topology_only",
        },
        "artifacts": artifacts,
        "evidence": evidence,
        "summary": {
            "required_artifacts": len(EXPECTED_SCHEMAS),
            "observed_artifacts": sum(row["input_state"] == "observed" for row in artifacts),
            "blocked_inputs": blocked_inputs,
            "blocked_observations": len(evidence["blocked"]),
            "unknown_observations": len(evidence["unknown"]),
            "inferred_observations": len(evidence["inferred"]),
        },
        "does_not_prove": [
            "Static graph declarations do not prove live runtime state.",
            "Artifact presence and hashes do not prove benchmark quality or endpoint availability.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-harness integration map", "",
        f"- Schema: `{report['schema']}`",
        f"- Generated artifacts: `{report['summary']['observed_artifacts']}`",
        f"- Static graph SHA-256: `{report['graph']['sha256']}`", "",
        "No runtime state is inferred from the static graph.", "",
    ]
    for title, key in (("Observed", "observed"), ("Inferred", "inferred"),
                       ("Blocked", "blocked"), ("Unknown", "unknown")):
        lines.extend([f"## {title}", ""])
        rows = report["evidence"][key]
        if rows:
            lines.extend(
                f"- `{row['artifact_id']}{row['pointer']}`: `{row['value']}`" for row in rows
            )
        else:
            lines.append("- None.")
        lines.append("")
    lines.extend(["## Artifact hashes", ""])
    lines.extend(
        f"- `{row['id']}` `{row['schema']}`: `{row['sha256']}`" for row in report["artifacts"]
    )
    lines.extend(["", "## Does not prove", ""])
    lines.extend(f"- {text}" for text in report["does_not_prove"])
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store(report: dict[str, Any], store_root: str, run_id: str,
           artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [store.put_receipt(
        kind="cross_harness_integration_map", body=report, run_id=run_id,
        verdict="CROSS_HARNESS_INTEGRATION_BLOCKED" if report.get("status") == "blocked_inputs" else "CROSS_HARNESS_INTEGRATION_MAPPED",
    )]
    for path_text, label in artifacts:
        if path_text and Path(path_text).is_file():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH))
    for flag in EXPECTED_SCHEMAS:
        parser.add_argument(f"--{flag.replace('_', '-')}", required=True)
    parser.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "cross_harness_integration_map.json"))
    parser.add_argument("--markdown-out", default=str(Path(tempfile.gettempdir()) / "cross_harness_integration_map.md"))
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)
    paths = {key: getattr(args, key) for key in EXPECTED_SCHEMAS}
    report = build_integration_map(graph_path=args.graph, artifact_paths=paths)
    json_path = _write(args.out, json.dumps(report, indent=2, sort_keys=True))
    markdown_path = _write(args.markdown_out, render_markdown(report))
    stored = _store(report, args.store_root, args.run_id, [
        (json_path, "cross-harness-integration-map-json"),
        (markdown_path, "cross-harness-integration-map-markdown"),
    ])
    if stored:
        report = {**report, "store_outputs": stored}
        _write(args.out, json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report.get("status") == "blocked_inputs" else 0


if __name__ == "__main__":
    raise SystemExit(main())
