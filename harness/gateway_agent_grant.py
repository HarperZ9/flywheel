"""Agent binding persistence and owner review metadata for exact grants."""
from .gateway_agent_binding import validate_agent_binding
from .gateway_operation import GatewayOperationError
from .plan_run_snapshot import thaw_json, freeze_json


def validate_record_fields(value, base):
    if type(value) is not dict: return False
    return set(value) == base or (value.get("action") == "agent.run"
                                 and set(value) == base | {"agent_binding"})


def record_binding(record, operation):
    if "agent_binding" in record:
        validate_agent_binding(record["agent_binding"], operation)


def attach_binding(record, plan):
    if plan.agent_binding is not None:
        record["agent_binding"] = thaw_json(plan.agent_binding)


def compare_binding(record, plan):
    if record["action"] != "agent.run": return
    if "agent_binding" not in record:
        raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    if freeze_json(record["agent_binding"]) != plan.agent_binding:
        raise GatewayOperationError("AGENT_BINDING_DRIFT")


def review_binding(record):
    binding = record.get("agent_binding")
    if binding is None: return {"status": "reprepare_required"}
    if binding.get('execution_mode') == 'native_cli_session':
        from .gateway_cli_binding import review_cli_binding
        return review_cli_binding(binding)
    review = {"schema": ("flywheel.gateway-agent-review/v2"
            if "tool_protocol" in binding else "flywheel.gateway-agent-review/v1"),
        "binding_sha256": freeze_json(binding).sha256,
        "endpoint": binding["endpoint"]["name"],
        "base_url": binding["endpoint"]["base_url"],
        "model": binding["model"], "root": binding["workspace"]["root"],
        "workspace_policy_sha256": binding["workspace"]["policy_sha256"],
        "budget": binding["budget"], "capabilities": binding["capabilities"]}
    if "tool_protocol" in binding:
        review["tool_protocol"] = binding["tool_protocol"]
    return review
