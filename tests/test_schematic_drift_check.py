from harness.schematic_drift import build_drift_report, render_markdown


def _graph():
    return {
        "schema": "harness.closed-loop-integration-graph/v1",
        "nodes": [
            {"id": "agentic_task_manifest_generator"},
            {"id": "cross_harness_manifest"},
            {"id": "embodied_realtime_plan"},
            {"id": "benchmark_execution_matrix"},
            {"id": "closed_loop_seed"},
            {"id": "closed_loop_outcome"},
            {"id": "objective_evidence_matrix"},
        ],
        "edges": [
            {"from": "agentic_task_manifest_generator", "to": "benchmark_execution_matrix"},
            {"from": "cross_harness_manifest", "to": "benchmark_execution_matrix"},
            {"from": "embodied_realtime_plan", "to": "benchmark_execution_matrix"},
            {"from": "benchmark_execution_matrix", "to": "closed_loop_seed"},
            {"from": "closed_loop_seed", "to": "closed_loop_outcome"},
        ],
    }


def test_schematic_drift_report_detects_missing_node_and_stale_text():
    graph = _graph()
    graph["nodes"] = [row for row in graph["nodes"] if row["id"] != "cross_harness_manifest"]
    report = build_drift_report(
        graph,
        graph_path="graph.json",
        report_text="The next highest-leverage implementation step is still a non-executing manifest generator.",
        required_files={},
    )

    assert report["schema"] == "harness.schematic-drift-check/v1"
    assert report["verdict"] == "SCHEMATIC_DRIFT"
    assert report["missing_nodes"] == ["cross_harness_manifest"]
    assert report["summary"]["stale_phrases"] == 1


def test_schematic_drift_markdown_declares_non_execution():
    report = build_drift_report(_graph(), graph_path="graph.json", required_files={})
    markdown = render_markdown(report)

    assert "# Schematic drift check" in markdown
    assert "Does not run tests." in markdown
