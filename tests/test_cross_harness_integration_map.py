import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_cross_harness_integration_map import build_integration_map, main, render_markdown


SCHEMAS = {
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


def _write(path: Path, body: dict) -> Path:
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    graph = _write(tmp_path / "graph.json", {
        "schema": "harness.closed-loop-integration-graph/v1",
        "status": "live",
        "nodes": [{"id": "static_only", "status": "live"}],
        "edges": [],
    })
    paths = {}
    for key, schema in SCHEMAS.items():
        body = {"schema": schema, "status": f"{key}_observed"}
        if key == "endpoint_gate":
            body["verdict"] = "MODEL_ENDPOINT_GATE_FAIL"
        if key == "comparison":
            body["conclusion"] = {"verdict": "COMPARISON_INSUFFICIENT"}
        paths[key] = _write(tmp_path / f"{key}.json", body)
    return graph, paths


def test_map_requires_hashes_and_preserves_generated_metadata(tmp_path):
    graph, paths = _fixture(tmp_path)

    result = build_integration_map(graph_path=graph, artifact_paths=paths)

    assert result["schema"] == "harness.cross-harness-integration-map/v1"
    assert result["status"] == "runtime_artifacts_mapped"
    assert [row["id"] for row in result["artifacts"]] == list(SCHEMAS)
    for row in result["artifacts"]:
        source = paths[row["id"]]
        assert row["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert row["schema"] == SCHEMAS[row["id"]]
        assert {item["value"] for item in row["observed_metadata"] if item["field"] == "status"} == {
            f"{row['id']}_observed"
        }
    assert result["evidence"]["inferred"] == [
        {
            "artifact_id": "graph",
            "field": "status",
            "pointer": "/nodes/0/status",
            "scope": "static_graph_declaration",
            "value": "live",
        }
    ]
    assert any(row["value"] == "MODEL_ENDPOINT_GATE_FAIL" for row in result["evidence"]["blocked"])
    assert any(row["value"] == "COMPARISON_INSUFFICIENT" for row in result["evidence"]["unknown"])


def test_static_graph_status_never_becomes_live_runtime_evidence(tmp_path):
    graph, paths = _fixture(tmp_path)

    result = build_integration_map(graph_path=graph, artifact_paths=paths)

    assert result["graph"]["path"] == str(graph)
    assert result["graph"]["schema"] == "harness.closed-loop-integration-graph/v1"
    assert result["graph"]["sha256"] == hashlib.sha256(graph.read_bytes()).hexdigest()
    assert result["graph"]["evidence_scope"] == "static_topology_only"
    assert all(row.get("artifact_id") != "graph" for row in result["evidence"]["observed"])
    assert not any(row.get("artifact_id") == "graph" for row in result["evidence"]["observed"])
    assert result["evidence"]["inferred"][0]["scope"] == "static_graph_declaration"


@pytest.mark.parametrize("missing", list(SCHEMAS))
def test_map_records_each_missing_required_artifact_as_blocked(tmp_path, missing):
    graph, paths = _fixture(tmp_path)
    paths[missing] = tmp_path / "missing.json"

    result = build_integration_map(graph_path=graph, artifact_paths=paths)

    row = next(row for row in result["artifacts"] if row["id"] == missing)
    assert row["sha256"] is None
    assert row["expected_schema"] == SCHEMAS[missing]
    assert row["schema"] is None
    assert row["input_state"] == "blocked"
    assert row["blocking_reason"] == f"{missing}_missing"
    assert result["status"] == "blocked_inputs"
    assert result["summary"]["observed_artifacts"] == 9
    assert result["summary"]["blocked_inputs"] == 1


def test_map_records_schema_mismatch_as_blocked(tmp_path):
    graph, paths = _fixture(tmp_path)
    _write(paths["coverage"], {"schema": "wrong", "status": "complete"})

    result = build_integration_map(graph_path=graph, artifact_paths=paths)

    row = next(row for row in result["artifacts"] if row["id"] == "coverage")
    assert row["sha256"] == hashlib.sha256(paths["coverage"].read_bytes()).hexdigest()
    assert row["expected_schema"] == SCHEMAS["coverage"]
    assert row["schema"] == "wrong"
    assert row["input_state"] == "blocked"
    assert row["blocking_reason"] == "coverage_schema_mismatch"


def test_valid_artifact_without_status_is_unknown(tmp_path):
    graph, paths = _fixture(tmp_path)
    _write(paths["coverage"], {"schema": SCHEMAS["coverage"]})

    result = build_integration_map(graph_path=graph, artifact_paths=paths)

    row = next(row for row in result["artifacts"] if row["id"] == "coverage")
    assert row["status"] is None
    assert row["verdict"] is None
    assert any(
        item["artifact_id"] == "coverage" and item["value"] == "status_or_verdict_absent"
        for item in result["evidence"]["unknown"]
    )


def test_markdown_separates_evidence_classes(tmp_path):
    graph, paths = _fixture(tmp_path)

    markdown = render_markdown(build_integration_map(graph_path=graph, artifact_paths=paths))

    assert "## Observed" in markdown
    assert "## Inferred" in markdown
    assert "## Blocked" in markdown
    assert "## Unknown" in markdown
    assert "No runtime state is inferred from the static graph." in markdown


def test_cli_writes_json_markdown_and_store_receipt(tmp_path):
    graph, paths = _fixture(tmp_path)
    out = tmp_path / "map.json"
    markdown = tmp_path / "map.md"
    argv = ["--graph", str(graph)]
    for key, path in paths.items():
        argv.extend([f"--{key.replace('_', '-')}", str(path)])
    argv.extend([
        "--out", str(out), "--markdown-out", str(markdown),
        "--store-root", str(tmp_path / "store"), "--run-id", "map-run",
    ])

    assert main(argv) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == (
        "harness.cross-harness-integration-map/v1"
    )
    assert "## Observed" in markdown.read_text(encoding="utf-8")
    receipts = (tmp_path / "store" / "receipts.jsonl").read_text(encoding="utf-8")
    assert "cross_harness_integration_map" in receipts


def test_cli_returns_nonzero_and_stores_blocked_verdict_for_missing_input(tmp_path):
    graph, paths = _fixture(tmp_path); paths["coverage"] = tmp_path / "missing.json"
    out, markdown = tmp_path / "map.json", tmp_path / "map.md"
    argv = ["--graph", str(graph)]
    for key, path in paths.items(): argv.extend([f"--{key.replace('_', '-')}", str(path)])
    argv.extend(["--out", str(out), "--markdown-out", str(markdown), "--store-root", str(tmp_path / "store"), "--run-id", "blocked"])
    assert main(argv) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "blocked_inputs"
    assert "CROSS_HARNESS_INTEGRATION_BLOCKED" in (tmp_path / "store" / "receipts.jsonl").read_text(encoding="utf-8")
