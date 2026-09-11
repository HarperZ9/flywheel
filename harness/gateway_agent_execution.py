"""Real-router execution with private evidence and metadata-only IPC."""
from __future__ import annotations

from pathlib import Path

from .credential_handles import CredentialBindings
from .gateway_agent_trace import AgentTrace, TraceError, TraceLedger


def run_private_agent(operation: dict, bindings: dict, repo_root: Path,
                      trace: AgentTrace, source_context, emit, *, binding=None, deadline=None) -> dict:
    from .effort import resolve_effort, stamp_applied
    import time
    from .gateway_agent_binding import validate_agent_binding
    from .gateway_agent_workspace import pinned_workspace
    from .gateway_agent_proposer import BoundAgentProposer
    from .gateway_operation import canonicalize_operation, materialize_agent_attachment, GatewayOperationError
    from .router_agent import run_router_agent
    from .source_context_worker import materialize_goal

    # Credentials travel only via the approved in-memory binding interface.
    # They are never copied to the request/evidence or ambient environment.
    if binding is None or type(deadline) not in (int, float):
        raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    validate_agent_binding(binding, canonicalize_operation("agent.run", operation))
    trace.append("request", {"operation": operation, "source_context": source_context, "execution_binding": binding})
    execution = materialize_agent_attachment(operation)
    ledger = TraceLedger(trace)
    rejected = []

    def progress(event):
        try:
            trace.append("progress", event)
            emit({"type": "progress", "event": trace.projection("running")})
        except Exception:
            rejected.append(True)
            raise TraceError() from None

    try:
        with pinned_workspace(binding["workspace"]) as root:
            goal = materialize_goal(execution["goal"], source_context)
            if binding.get('execution_mode') == 'native_cli_session':
                from .gateway_cli_execution import run_cli_session
                result = run_cli_session(goal, binding, root, deadline, progress,
                    state_root=trace.root, state_identity=trace.identity)
            elif binding.get("tool_protocol", {}).get("protocol") == "native":
                from .gateway_agent_native_tools import run_native_tool_agent
                result = run_native_tool_agent(goal, binding,
                    CredentialBindings(bindings), root, ledger, deadline,
                    on_event=progress, test_cmd=execution.get("test_cmd"))
            else:
                proposer = BoundAgentProposer(binding, CredentialBindings(bindings), ledger, deadline)
                result = run_router_agent(
                    goal, binding["endpoint"]["name"], root=str(root),
                    allow_write=binding["capabilities"]["allow_write"],
                    allow_exec=binding["capabilities"]["allow_exec"], max_steps=binding["budget"]["max_steps"],
                    model=binding["model"]["model_id"], max_tokens=binding["budget"]["max_tokens"],
                    temperature=binding["sampling"]["temperature"], seed=binding["sampling"]["router_seed"],
                    proposer=proposer, test_cmd=execution.get("test_cmd"),
                    credential_bindings=CredentialBindings(bindings),
                    on_event=progress, ledger=ledger, event_errors_fatal=True)
            if time.monotonic() >= deadline:
                raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
        if rejected:
            raise TraceError()
        if operation.get("effort"):
            result["effort"] = stamp_applied(resolve_effort(operation["effort"]),
                max_steps_applied=operation["max_steps"], n_candidates_applied=False)
        trace.append("result", result)
        return trace.projection("completed", runtime=result.get("environment", {}))
    except Exception as exc:
        try:
            trace.append("failure", {"error_type": type(exc).__name__, "message": str(exc)})
        except Exception:
            pass  # rejected credentials/custody never enter the diagnostic record
        raise



def trace_from_request(context: dict, secrets=()) -> AgentTrace:
    if (type(context) is not dict or set(context) != {
            "state_root", "state_root_identity", "owner_ref", "journey_ref", "operation_ref"}
            or type(context["state_root"]) is not str):
        raise TraceError()
    return AgentTrace(Path(context["state_root"]), context["owner_ref"],
        context["journey_ref"], context["operation_ref"], secrets=secrets,
        expected_identity=context["state_root_identity"])


def trace_context(authorized, state_root: Path) -> dict:
    from .gateway_operation_route import operation_ref_for
    from .private_artifact_fs import root_identity
    return {"state_root": str(state_root),
        "state_root_identity": root_identity(state_root).to_json_dict(),
        "owner_ref": authorized.owner_ref, "journey_ref": authorized.journey_ref,
        "operation_ref": operation_ref_for(authorized.owner_ref,
            authorized.journey_ref, authorized.client_request_id)}


def recovered_projection(state_root, owner, journey, operation, state, reason=None):
    trace = AgentTrace(state_root, owner, journey, operation)
    if not trace.read():
        return None
    return trace.projection(state, reason=reason)
