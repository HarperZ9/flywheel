"""MCP admission witness metadata extraction for local tool calls."""
from __future__ import annotations

import re

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def mcp_admission_context(spec: dict) -> dict:
    meta = spec.get("admission_metadata")
    if not isinstance(meta, dict):
        return {}
    fields = {
        "mcp_admission_sha256": meta.get("admission_sha256"),
        "mcp_discovery_receipt_sha256": meta.get("discovery_receipt_sha256"),
        "mcp_server_descriptor_sha256": meta.get("server_descriptor_sha256"),
        "mcp_tool_descriptor_sha256": meta.get("tool_descriptor_sha256"),
        "mcp_config_sha256": meta.get("config_sha256"),
    }
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None
           for value in fields.values()):
        return {}
    return {"admission": "MCP_ADMITTED", **fields}
