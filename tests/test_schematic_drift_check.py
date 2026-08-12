from harness.schematic_drift import build_drift_report, render_markdown


def _graph():
    return {
        "schema": "harness.closed-loop-integration-graph/v1",
        "nodes": [
            {"id": "agentic_task_manifest_generator"},
            {"id": "cross_harness_manifest"},
            {"id": "adapter_runtime_matrix"},
            {"id": "endpoint_gates"},
            {"id": "forum_route_receipts"},
            {"id": "mcp_tool_health"},
            {"id": "embodied_realtime_plan"},
            {"id": "benchmark_execution_matrix"},
            {"id": "closed_loop_seed"},
            {"id": "closed_loop_outcome"},
            {"id": "benchmark_coverage"},
            {"id": "harness_comparison"},
            {"id": "cross_harness_executor"},
            {"id": "objective_evidence_matrix"},
        ],
        "edges": [
            {"from": "agentic_task_manifest_generator", "to": "benchmark_execution_matrix"},
            {"from": "cross_harness_manifest", "to": "benchmark_execution_matrix"},
            {"from": "adapter_runtime_matrix", "to": "benchmark_execution_matrix"},
            {"from": "forum_route_receipts", "to": "closed_loop_seed"},
            {"from": "mcp_tool_health", "to": "closed_loop_seed"},
            {"from": "embodied_realtime_plan", "to": "benchmark_execution_matrix"},
            {"from": "benchmark_execution_matrix", "to": "closed_loop_seed"},
            {"from": "closed_loop_seed", "to": "closed_loop_outcome"},
            {"from": "cross_harness_manifest", "to": "cross_harness_executor"},
            {"from": "adapter_runtime_matrix", "to": "cross_harness_executor"},
            {"from": "endpoint_gates", "to": "cross_harness_executor"},
            {"from": "cross_harness_executor", "to": "benchmark_coverage"},
            {"from": "cross_harness_executor", "to": "harness_comparison"},
            {"from": "cross_harness_executor", "to": "closed_loop_seed"},
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


def test_schematic_drift_requires_executor_topology():
    graph = _graph()
    report = build_drift_report(graph, graph_path="graph.json", required_files={})

    assert report["missing_nodes"] == []
    assert report["missing_edges"] == []

    graph["edges"] = [row for row in graph["edges"] if row["from"] != "endpoint_gates"]
    report = build_drift_report(graph, graph_path="graph.json", required_files={})
    assert report["missing_edges"] == [
        {"from": "endpoint_gates", "to": "cross_harness_executor"}
    ]


def test_schematic_drift_blocks_non_integration_map_report():
    report = build_drift_report(
        _graph(),
        graph_path="graph.json",
        report_path="report.md",
        report_text="# unrelated report\n- Schema: `harness.comparison-report/v1`\n",
        required_files={},
    )

    assert report["verdict"] == "SCHEMATIC_DRIFT"
    assert report["report_input_errors"] == ["integration_map_schema_mismatch"]
