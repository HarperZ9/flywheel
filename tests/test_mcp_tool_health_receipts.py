from scripts.run_mcp_tool_health_receipts import build_report, classify, parse_observations, split_names


def test_split_names_trims_empty_items():
    assert split_names("index, forum,,telos ") == ["index", "forum", "telos"]


def test_parse_observations_uses_pipe_fields():
    observations = parse_observations([
        "index=TRANSPORT_CLOSED|transport_closed|Transport closed",
        "forum=MATCH||project-telos",
    ])

    assert observations["index"]["status"] == "TRANSPORT_CLOSED"
    assert observations["index"]["error_code"] == "transport_closed"
    assert observations["index"]["summary"] == "Transport closed"
    assert observations["forum"]["status"] == "MATCH"
    assert observations["forum"]["summary"] == "project-telos"


def test_classify_distinguishes_health_states():
    assert classify(root_exists=True, observed_status="MATCH") == "OBSERVED_HEALTHY"
    assert classify(root_exists=True, observed_status="TRANSPORT_CLOSED") == "OBSERVED_DEGRADED"
    assert classify(root_exists=True, observed_status="") == "CONFIGURED_UNOBSERVED"
    assert classify(root_exists=False, observed_status="") == "MISSING_ROOT"


def test_build_report_records_observed_and_configured_tools():
    report = build_report(
        tools=["index", "forum"],
        observations={
            "index": {
                "status": "TRANSPORT_CLOSED",
                "error_code": "transport_closed",
                "summary": "Transport closed",
            },
            "forum": {
                "status": "MATCH",
                "error_code": "",
                "summary": "project-telos",
            },
        },
    )

    assert report["schema"] == "harness.mcp-tool-health/v1"
    assert report["summary"]["observed_tools"] == 2
    assert report["summary"]["healthy_observed_tools"] == 1
    assert report["summary"]["degraded_observed_tools"] == 1
    assert report["summary"]["degraded_tools"] == ["index"]
    assert report["tools"][0]["provider_execution_observed"] is False


def test_default_tool_profiles_include_pubscan():
    report = build_report(tools=["pubscan"], observations={})

    assert report["tools"][0]["tool"] == "pubscan"
    assert report["tools"][0]["role"] == "public-scan-tooling"
