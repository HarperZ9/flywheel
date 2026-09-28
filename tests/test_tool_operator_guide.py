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
                    "cli": ["index"],
                    "mcp": ["index_graph.mcp"],
                    "harness_commands": ["mcp-health", "readiness tools"],
                },
                "entrypoint_metadata": {
                    "cli_source": "pyproject_project_scripts",
                    "cli_limit": "metadata declaration only; not installed or exercised",
                    "project_scripts": {
                        "status": "declared",
                        "source": {
                            "filename": "pyproject.toml",
                            "sha256": "0" * 64,
                        },
                    },
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
    assert "metadata declaration only" in guide["tools"][0]["how_to_operate"]
    assert "# Tool operator guide" in markdown
    assert "Metadata declaration only" in markdown


def test_tool_operator_guide_preserves_unverified_profile_labels(tmp_path):
    source = tmp_path / "contract.json"
    contract = {
        "schema": "harness.tool-integration-contract/v1",
        "tools": [
            {
                "tool": "relay",
                "role": "agent-bridge",
                "root": str(tmp_path / "relay"),
                "root_exists": True,
                "packaged_mode": "external_repo_sidecar",
                "required_for": ["harness interop"],
                "state_contracts": ["event transport envelope"],
                "entrypoints": {
                    "cli": [],
                    "mcp": [],
                    "harness_commands": ["readiness tools", "tool-contract"],
                },
                "entrypoint_metadata": {
                    "cli_source": "unverified_profile",
                    "cli_limit": "unverified fallback profile; metadata missing or invalid",
                    "project_scripts": {
                        "status": "absent",
                        "source": {
                            "filename": "pyproject.toml",
                            "sha256": None,
                        },
                    },
                    "fallback_profile": {"status": "unverified_profile"},
                },
                "readiness": {"verdict": "PROTOTYPE_WITH_GAPS", "score": 0.5, "enterprise_ready": False},
            }
        ],
    }
    source.write_text(json.dumps(contract), encoding="utf-8")

    guide = build_guide(contract, source_contract=source)
    markdown = render_markdown(guide)

    assert "unverified fallback profile" in guide["tools"][0]["how_to_operate"]
    assert "Unverified fallback profile" in markdown
