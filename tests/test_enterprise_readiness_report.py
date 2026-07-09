import json

from scripts.run_enterprise_readiness_report import build_report, render_markdown


def test_enterprise_readiness_report_extracts_mneme_relay_plexus(tmp_path):
    contract = tmp_path / "tool_contract.json"
    contract.write_text(json.dumps({
        "schema": "harness.tool-integration-contract/v1",
        "tools": [
            {
                "tool": "mneme",
                "role": "memory-provenance",
                "root": "C:/dev/public/mneme",
                "root_exists": True,
                "packaged_mode": "external_repo_sidecar",
                "entrypoints": {"cli": [], "mcp": ["mneme.mcp"], "harness_commands": []},
                "readiness": {"score": 0.6, "verdict": "PROTOTYPE_WITH_GAPS", "present_total": 12, "required_total": 20},
                "state_contracts": ["memory provenance receipt"],
            },
            {
                "tool": "relay",
                "role": "event-transport",
                "root": "C:/dev/public/relay",
                "root_exists": True,
                "packaged_mode": "external_repo_sidecar",
                "entrypoints": {"cli": ["python serve.py"], "mcp": [], "harness_commands": []},
                "readiness": {"score": 0.2778, "verdict": "PROTOTYPE_WITH_GAPS", "present_total": 5, "required_total": 18},
                "state_contracts": [],
            },
            {
                "tool": "plexus",
                "role": "agent-protocol",
                "root": "C:/dev/public/plexus",
                "root_exists": True,
                "packaged_mode": "external_repo_sidecar",
                "entrypoints": {"cli": ["python -m plexus"], "mcp": ["plexus.mcp"], "harness_commands": []},
                "readiness": {"score": 0.85, "verdict": "RELEASE_CANDIDATE", "present_total": 17, "required_total": 20},
                "state_contracts": ["protocol contract"],
            },
        ],
    }), encoding="utf-8")

    report = build_report(tool_contract_path=contract, tools=["mneme", "relay", "plexus"])

    assert report["schema"] == "harness.enterprise-readiness-report/v1"
    assert report["summary"]["tools_reported"] == 3
    assert "mneme" in report["reports"]
    assert report["reports"]["relay"]["release_lane"] == "FOUNDATION_PRESENT"
    assert report["summary"]["hardening_required_count"] == 2


def test_enterprise_readiness_markdown_lists_tool_lanes(tmp_path):
    contract = tmp_path / "missing.json"
    report = build_report(tool_contract_path=contract, tools=["mneme"])
    markdown = render_markdown(report)

    assert "# Enterprise readiness report" in markdown
    assert "Tool lanes" in markdown
