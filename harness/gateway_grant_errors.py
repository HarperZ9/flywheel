"""Fixed public failures for gateway grant and operation routes."""
from __future__ import annotations

from .evidence_public import TransportError, error_response
from .journey_lock import JourneyLockBusy
from .journey_store import JourneyStoreError


def gateway_error_response(exc: Exception) -> tuple[dict, int]:
    code = getattr(exc, "code", "STORE_COMMIT_FAILED")
    if isinstance(exc, TransportError):
        code = "INVALID_REQUEST"
    elif isinstance(exc, JourneyLockBusy):
        code = "STORE_BUSY"
    elif isinstance(exc, JourneyStoreError) and code == "JOURNEY_NOT_FOUND":
        code = "PERMISSION_REQUIRED"
    errors = {
        "INVALID_REQUEST": (422, "gateway operation is invalid"),
        "AGENT_BINDING_DRIFT": (409, "agent execution authority changed"),
        "AGENT_REPREPARE_REQUIRED": (409, "agent execution requires a new proposal"),
        "AGENT_MODEL_MISMATCH": (409, "provider reported a different model"),
        "AGENT_ENDPOINT_UNSUPPORTED": (422, "endpoint does not support bound agent execution"),
        "AGENT_MCP_RUNTIME_DRIFT": (
            409, "admitted MCP runtime changed before execution"),
        "AGENT_MCP_TOOL_COLLISION": (
            422, "admitted MCP tool names collide"),
        "AGENT_MCP_TOOL_SHADOWS_BUILTIN": (
            422, "admitted MCP tool shadows a builtin tool"),
        "AGENT_MCP_SCHEMA_UNSUPPORTED": (
            422, "admitted MCP tool schema is unsupported by the native route"),
        "MCP_DISCOVERY_STARTUP_NOT_AUTHORIZED": (
            403, "MCP discovery startup requires explicit approval"),
        "MCP_DISCOVERY_RECEIPT_UNAVAILABLE": (
            409, "MCP discovery receipt is unavailable"),
        "MCP_DISCOVERY_RECEIPT_STALE": (
            409, "MCP discovery receipt is stale"),
        "MCP_DISCOVERY_CONFIG_DRIFT": (
            409, "MCP catalog launch changed since discovery"),
        "MCP_CACHE_UNAVAILABLE": (
            503, "MCP discovery cache is unavailable"),
        "MCP_CATALOG_LAUNCH_UNAVAILABLE": (
            503, "MCP catalog launch is unavailable"),
        "MCP_CREDENTIAL_VERSION_UNAVAILABLE": (
            422, "MCP credential version pinning is unavailable"),
        "MCP_AUTHORITY_UNAVAILABLE": (
            422, "MCP tool authority is unavailable"),
        "MCP_AMBIENT_ENV_UNSUPPORTED": (
            422, "MCP ambient environment launch is unsupported"),
        "MCP_HTTP_TRANSPORT_UNSUPPORTED": (
            422, "MCP HTTP transport admission is unsupported"),
        "MCP_CRITICAL_TOOL_UNSUPPORTED": (
            422, "critical MCP tool authority is unsupported"),
        "OPERATION_DEADLINE_EXCEEDED": (504, "agent execution budget expired"),
        "BULLETIN_ORIGIN_REQUIRED": (422, "Bulletin origin requires a new exact grant"),
        "BULLETIN_ORIGIN_INVALID": (422, "Bulletin origin is invalid"),
        "BULLETIN_ORIGIN_MISMATCH": (409, "Bulletin configured origin differs from approval"),
        "AUTH_REQUIRED": (401, "gateway authentication is required"),
        "PERMISSION_REQUIRED": (403, "gateway operation approval is required"),
        "PERMISSION_DENIED": (403, "gateway operation approval is invalid"),
        "APPROVAL_EXPIRED": (403, "gateway operation approval expired"),
        "NOT_FOUND": (404, "gateway operation was not found"),
        "LANE_UNAVAILABLE": (503, "lane runtime is unavailable; inspect Lanes for details"),
        "HEAD_CONFLICT": (409, "Journey head changed"),
        "PLAN_BINDING_DRIFT": (
            409, "plan run does not match its forged contract"),
        "SOURCE_DRIFT": (409, "source changed since continuation preview"),
        "PREVIEW_MISMATCH": (
            409, "continuation preview does not match request"),
        "CONTINUATION_BLOCKED": (409, "continuation source is incomplete"),
        "CONTINUATION_ROOT_MISMATCH": (
            422, "continuation runner root mismatch"),
        "CONTINUATION_CONTEXT_MISMATCH": (
            422, "continuation runner context mismatch"),
        "CONTINUATION_NOT_STARTED": (
            409, "continuation has not been started"),
        "CONTINUATION_JOURNEY_MISMATCH": (
            409, "continuation Journey mismatch"),
        "CONTINUATION_BINDING_DRIFT": (
            409, "continuation start binding changed"),
        "INVALID_CONTINUATION": (422, "continuation preview is invalid"),
        "PREVIEW_NOT_FOUND": (404, "continuation preview was not found"),
        "IDEMPOTENCY_MISMATCH": (
            409, "operation request conflicts with its prior use"),
        "INVALID_TRANSITION": (
            409, "operation state does not allow this action"),
        "CANCEL_UNAVAILABLE": (
            409, "operation cancellation is unavailable"),
        "STORE_BUSY": (503, "operation store is busy"),
        "STORE_COMMIT_FAILED": (
            500, "operation state could not be committed"),
        "SOURCE_CONTEXT_PERMISSION_DENIED": (
            403, "source context is not available to this owner"),
        "SOURCE_CONTEXT_REF_NOT_FOUND": (
            404, "source context reference was not found"),
        "SOURCE_CONTEXT_STORE_CORRUPT": (
            409, "source context snapshot is invalid"),
        "SOURCE_CONTEXT_AUTHORITY_BUSY": (
            503, "source context authority is busy"),
        "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE": (
            409, "source context authority is unavailable"),
        "SOURCE_CONTEXT_FAILED": (
            409, "source context snapshot is invalid"),
        "EXTERNAL_ACTION_FAILED": (
            502, "authorized external action failed")}
    code = code if code in errors else "STORE_COMMIT_FAILED"
    status, message = errors[code]
    return error_response(TransportError(code, message, status))
