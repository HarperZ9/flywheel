"""Owner-visible summaries of frozen operation proposals."""
from .gateway_operation import PROPOSAL_SCHEMA, thaw_operation

def proposal_response(record: dict, operation) -> dict:
    summary = {
        "schema": "flywheel.gateway-grant-summary/v1", "action": record["action"],
        "journey_ref": record["journey_ref"],
        "expected_event_head": record["expected_event_head"],
        "destination": dict(operation.destination), "tool": operation.tool,
        "operation_sha256": operation.operation_sha256,
        "arguments_sha256": operation.arguments_sha256,
        "scopes": list(operation.scopes), "data_refs": list(operation.data_refs),
        "credential_refs": list(operation.credential_refs),
        "effect": "one dispatch after approval", "expires_at": record["expires_at"],
    }
    if record["action"] == "hook.run":
        rows = thaw_operation(operation.operation)["registrations"]
        summary["hook_registrations"] = [{k: row[k] for k in (
            "hook_id", "hook_sha256", "argv", "blocking")} for row in rows]
    if record["action"] == "lane.call":
        from .outcome_bulletin_media import proposal_review as _br; mr = _br(operation)
        if mr is not None: summary["bulletin_media_review"] = mr
    if record["action"] == "agent.run":
        from .gateway_agent_grant import review_binding
        summary["agent_execution"] = review_binding(record)
    return {
        "schema": PROPOSAL_SCHEMA, "proposal_ref": record["proposal_ref"],
        "planned_grant_ref": record["planned_grant_ref"],
        "action": record["action"], "journey_ref": record["journey_ref"],
        "expected_event_head": record["expected_event_head"],
        "client_request_id": record["client_request_id"], "tool": operation.tool,
        "destination": dict(operation.destination),
        "operation_sha256": operation.operation_sha256,
        "arguments_sha256": operation.arguments_sha256,
        "scopes": list(operation.scopes), "data_refs": list(operation.data_refs),
        "credential_refs": list(operation.credential_refs),
        "expires_at": record["expires_at"], "summary": summary,
    }
