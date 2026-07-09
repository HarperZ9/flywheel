import json

from scripts.run_index_receipt import build_index_command, summarize_result


def test_build_index_command_context_envelope_with_focus():
    command = build_index_command(
        python_exe="python",
        lane="context-envelope",
        root="C:/dev",
        budget=12000,
        focus="local-model harness",
        hops=2,
        max_docs=500,
        freshness=False,
    )

    assert command == [
        "python",
        "-m",
        "index_graph.cli",
        "context-envelope",
        "--root",
        "C:/dev",
        "--budget",
        "12000",
        "--json",
        "--focus",
        "local-model harness",
        "--hops",
        "2",
    ]


def test_summarize_result_marks_valid_json_as_match():
    payload = {"schema": "index.context-envelope/v1", "ok": True}
    receipt = summarize_result(
        lane="context-envelope",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=0,
        elapsed_ms=12,
        stdout=json.dumps(payload),
        stderr="",
        artifact_path="C:/tmp/index.json",
    )

    assert receipt["schema"] == "harness.index-cli-receipt/v1"
    assert receipt["verdict"] == "MATCH"
    assert receipt["output_json_valid"] is True
    assert receipt["output_schema"] == "index.context-envelope/v1"
    assert receipt["failure_code"] == ""
    assert receipt["mcp_observation"]["status"] == "unobserved"
    assert receipt["mcp_observation"]["observed"] is False


def test_summarize_result_fails_closed_on_invalid_json():
    receipt = summarize_result(
        lane="context-envelope",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=0,
        elapsed_ms=12,
        stdout="not json",
        stderr="",
        artifact_path="C:/tmp/index.json",
    )

    assert receipt["verdict"] == "UNVERIFIABLE"
    assert receipt["failure_code"] == "invalid_json"


def test_summarize_result_fails_closed_on_timeout():
    receipt = summarize_result(
        lane="router",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=None,
        elapsed_ms=120000,
        stdout="",
        stderr="",
        artifact_path="",
        timed_out=True,
    )

    assert receipt["verdict"] == "UNVERIFIABLE"
    assert receipt["failure_code"] == "timeout"


def test_summarize_result_uses_valid_stale_artifact_on_timeout():
    payload = {"schema": "project-telos.context-envelope/v1", "ok": True}
    receipt = summarize_result(
        lane="context-envelope",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=None,
        elapsed_ms=120000,
        stdout="",
        stderr="",
        artifact_path="C:/tmp/index.json",
        timed_out=True,
        stale_stdout=json.dumps(payload),
        stale_artifact_path="C:/tmp/index.json",
    )

    assert receipt["verdict"] == "DEGRADED_MATCH"
    assert receipt["failure_code"] == ""
    assert receipt["live_failure_code"] == "timeout"
    assert receipt["effective_output_source"] == "stale_artifact"
    assert receipt["stale_artifact_used"] is True
    assert receipt["stale_artifact_valid"] is True
    assert receipt["output_json_valid"] is True
    assert receipt["output_schema"] == "project-telos.context-envelope/v1"


def test_summarize_result_rejects_invalid_stale_artifact():
    receipt = summarize_result(
        lane="context-envelope",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=None,
        elapsed_ms=120000,
        stdout="",
        stderr="",
        artifact_path="C:/tmp/index.json",
        timed_out=True,
        stale_stdout="not json",
        stale_artifact_path="C:/tmp/index.json",
    )

    assert receipt["verdict"] == "UNVERIFIABLE"
    assert receipt["failure_code"] == "timeout"
    assert receipt["live_failure_code"] == "timeout"
    assert receipt["effective_output_source"] == "live_stdout"
    assert receipt["stale_artifact_used"] is False
    assert receipt["stale_artifact_valid"] is False


def test_summarize_result_records_mcp_transport_observation():
    receipt = summarize_result(
        lane="context-envelope",
        root="C:/dev",
        index_root="C:/dev/public/index",
        command=["python"],
        returncode=None,
        elapsed_ms=7,
        stdout="",
        stderr="",
        artifact_path="C:/tmp/index.json",
        timed_out=True,
        mcp_tool="index_context_envelope",
        mcp_status="transport_closed",
        mcp_error_code="transport_closed",
        mcp_error_summary="Transport closed",
    )

    assert receipt["verdict"] == "UNVERIFIABLE"
    assert receipt["mcp_observation"] == {
        "tool": "index_context_envelope",
        "status": "transport_closed",
        "error_code": "transport_closed",
        "error_summary": "Transport closed",
        "observed": True,
    }
