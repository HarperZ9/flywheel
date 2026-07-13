from scripts.run_codex_mcp_launch_contract import build_contract, render_markdown


def test_codex_mcp_contract_records_launch_profile_without_env_values(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[mcp_servers.index]
command = "python"
args = ["-m", "index_graph", "mcp"]
cwd = "C:/dev/public/index"

[mcp_servers.index.env]
PYTHONPATH = "C:/dev/public/index/src"
PYTHONIOENCODING = "utf-8"
""".strip(),
        encoding="utf-8",
    )

    contract = build_contract(
        codex_config=config,
        tools=["index"],
        observed=["index=TRANSPORT_CLOSED|Transport closed"],
    )

    assert contract["schema"] == "harness.codex-mcp-launch-contract/v1"
    assert contract["summary"]["servers_expected"] == 1
    assert contract["summary"]["servers_ready"] == 1
    assert contract["servers"][0]["configured"]["env_values_recorded"] is False
    assert contract["servers"][0]["fallback_commands"]
    assert contract["session_reload_boundary"]["code_or_config_fix_requires_host_reload"] is True


def test_codex_mcp_contract_markdown_names_reload_boundary(tmp_path):
    contract = build_contract(
        codex_config=tmp_path / "missing.toml",
        tools=["index"],
        observed=[],
    )

    markdown = render_markdown(contract)

    assert "# Codex MCP launch contract" in markdown
    assert "Reload boundary" in markdown
    assert "transport closed" in markdown
