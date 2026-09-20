from harness.local_tools import ToolExecutor, ToolGate


def test_action_witness_records_mcp_admission_identity(tmp_path):
    """Catches MCP calls whose in-memory action witness loses admitted tool identity."""
    meta = {
        "admission_sha256": "a" * 64,
        "discovery_receipt_sha256": "b" * 64,
        "server_descriptor_sha256": "c" * 64,
        "tool_descriptor_sha256": "d" * 64,
        "config_sha256": "e" * 64,
    }
    executor = ToolExecutor(
        root=str(tmp_path),
        gate=ToolGate(False, False, True),
        external={
            "mcp_index__index_doctor": {
                "fn": lambda _args: (True, "doctor ok"),
                "description": "Index doctor.",
                "admission": "MCP_ADMITTED:admission={}:receipt={}:server={}:tool={}".format(
                    meta["admission_sha256"],
                    meta["discovery_receipt_sha256"],
                    meta["server_descriptor_sha256"],
                    meta["tool_descriptor_sha256"],
                ),
                "admission_metadata": meta,
            }
        },
    )
    executor.init_receipt_chain("run-mcp")

    result = executor.execute("mcp_index__index_doctor", {})

    assert result.ok is True
    contexts = [record["context"] for record in executor.action_witness_records()]
    assert len(contexts) == 2
    for context in contexts:
        assert context["capability"] == "external-mcp"
        assert context["admission"] == "MCP_ADMITTED"
        assert context["mcp_admission_sha256"] == meta["admission_sha256"]
        assert context["mcp_discovery_receipt_sha256"] == meta["discovery_receipt_sha256"]
        assert context["mcp_server_descriptor_sha256"] == meta["server_descriptor_sha256"]
        assert context["mcp_tool_descriptor_sha256"] == meta["tool_descriptor_sha256"]
        assert context["mcp_config_sha256"] == meta["config_sha256"]
