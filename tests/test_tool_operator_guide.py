import json

from scripts.run_tool_operator_guide import build_guide, render_markdown


def test_tool_operator_guide_summarizes_contract_rows(tmp_path):
    source = tmp_path / "contract.json"
    contract = {
        "schema": "harness.tool-integration-contract/v1",
        "tools": [
            {
                "tool": "index",
                "role": "workspace-index",
                "root": "C:/dev/public/index",
                "root_exists": True,
                "packaged_mode": "external_repo_sidecar",
                "required_for": ["workspace context map"],
                "state_contracts": ["metadata root map"],
                "entrypoints": {
                    "cli": ["python -m index_graph.cli"],
                    "mcp": ["index_graph.mcp"],
                    "harness_commands": ["mcp-health", "readiness tools"],
                },
                "readiness": {"verdict": "PROTOTYPE_WITH_GAPS", "score": 0.8, "enterprise_ready": False},
            }
        ],
    }
    source.write_text(json.dumps(contract), encoding="utf-8")

    guide = build_guide(contract, source_contract=source)
    markdown = render_markdown(guide)

    assert guide["schema"] == "harness.tool-operator-guide/v1"
    assert guide["summary"]["tools"] == 1
    assert guide["tools"][0]["tool"] == "index"
    assert "workspace context map" in guide["tools"][0]["what_it_does"]
    assert "mcp-health" in guide["tools"][0]["how_to_operate"]
    assert "# Tool operator guide" in markdown
