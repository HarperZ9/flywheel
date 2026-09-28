"""Authenticated Rowan MCP discovery and selection route helpers."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_sha256
from .evidence_public import exact_request, parse_json
from .gateway_agent_mcp_admission import REQUEST_SCHEMA
from .gateway_agent_mcp_authority import trusted_catalog_selections
from .gateway_agent_mcp_cache import (
    cache_mcp_discovery_receipt,
    restricted_catalog_launch,
)
from .gateway_grant_errors import gateway_error_response
from .gateway_operation import GatewayOperationError
from .gateway_secret_boundary import validate_no_raw_secrets
from .operation_grants import _validate_owner_ref

CATALOG_SCHEMA = "flywheel.agent-mcp-catalog/v1"
DISCOVERY_REQUEST_SCHEMA = "flywheel.agent-mcp-discovery-request/v1"
DISCOVERY_RESPONSE_SCHEMA = "flywheel.agent-mcp-discovery-response/v1"


def agent_mcp_get(path: str, *, owner_ref: str, state_root: Path) -> tuple[dict, int]:
    try:
        if path != "/api/agent/mcp/catalog":
            raise GatewayOperationError("NOT_FOUND")
        _validate_owner_ref(owner_ref)
        Path(state_root)
        servers = [_catalog_server(row) for row in trusted_catalog_selections()]
        return {"schema": CATALOG_SCHEMA, "servers": servers,
                "catalog_sha256": canonical_sha256({"servers": servers})}, 200
    except Exception as exc:
        return gateway_error_response(exc)


def agent_mcp_post(path: str, raw: bytes | str, *, owner_ref: str,
                   state_root: Path) -> tuple[dict, int]:
    try:
        if path != "/api/agent/mcp/discovery-receipts":
            raise GatewayOperationError("NOT_FOUND")
        req = parse_json(raw)
        exact_request(req, {"schema", "server_id", "catalog_ref", "tools",
                            "timeout_s"},
                      optional={"discovery_authorization"})
        if req.get("schema") != DISCOVERY_REQUEST_SCHEMA:
            raise GatewayOperationError("INVALID_REQUEST")
        validate_no_raw_secrets(req)
        receipt = cache_mcp_discovery_receipt(
            req["catalog_ref"], server_id=req["server_id"],
            owner_ref=owner_ref, state_root=Path(state_root),
            tools=req["tools"], timeout_s=req["timeout_s"],
            discovery_authorization=req.get("discovery_authorization"))
        admission = {
            "schema": REQUEST_SCHEMA,
            "servers": [{
                "server_id": receipt["server_id"],
                "catalog_ref": receipt["catalog_ref"],
                "receipt_sha256": receipt["receipt_sha256"],
                "tools": list(receipt["selected_tools"]),
                "timeout_s": receipt["timeout_s"],
            }],
        }
        validate_no_raw_secrets(admission)
        review = _receipt_review(receipt)
        return {"schema": DISCOVERY_RESPONSE_SCHEMA,
                "mcp_admission": admission,
                "mcp_admission_sha256": canonical_sha256(admission),
                "receipt": review}, 200
    except Exception as exc:
        return gateway_error_response(exc)


def _catalog_server(row: dict) -> dict:
    catalog_ref = str(row["catalog_ref"])
    tools = [dict(tool) for tool in row["tools"]]
    server = {"server_id": str(row["server_id"]),
              "catalog_ref": catalog_ref,
              "availability": {"status": "available"},
              "tools": tools}
    try:
        launch, _kind = restricted_catalog_launch(
            catalog_ref, [tool["source_tool_name"] for tool in tools])
        server["launch"] = _launch_review(launch)
    except GatewayOperationError as exc:
        server["availability"] = {"status": "unavailable", "code": exc.code}
    return server


def _receipt_review(receipt: dict) -> dict:
    launch = receipt["launch"]
    return {
        "server_id": receipt["server_id"],
        "catalog_ref": receipt["catalog_ref"],
        "receipt_sha256": receipt["receipt_sha256"],
        "expires_at_unix": receipt["expires_at_unix"],
        "selected_tools": list(receipt["selected_tools"]),
        "config_sha256": receipt["config_sha256"],
        "descriptor_sha256": receipt["descriptor_sha256"],
        "tools_list_sha256": receipt["tools_list_sha256"],
        "authority_source": receipt["authority_source"],
        "launch": {
            "transport": launch["transport"],
            "inherit_env": launch["inherit_env"],
            "url_selected": bool(launch["url"]),
            "hide_window": launch["hide_window"],
            "allowed_tools": launch["allowed_tools"],
            "env_override_keys": [key for key, _value in launch["env_overrides"]],
        },
        "does_not_prove": list(receipt["does_not_prove"]),
    }


def _launch_review(launch) -> dict:
    return {
        "transport": "stdio",
        "inherit_env": launch.inherit_env,
        "url_selected": bool(launch.url),
        "hide_window": launch.hide_window,
        "allowed_tools": None if launch.allowed_tools is None else list(launch.allowed_tools),
        "env_override_keys": [key for key, _value in launch.env_overrides],
    }
