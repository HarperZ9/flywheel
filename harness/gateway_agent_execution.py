"""Real-router execution with private evidence and metadata-only IPC."""
from __future__ import annotations

from pathlib import Path

from .credential_handles import CredentialBindings
from .gateway_agent_trace import AgentTrace, TraceError, TraceLedger


def run_private_agent(operation: dict, bindings: dict, repo_root: Path,
                      trace: AgentTrace, source_context, emit) -> dict:
    from .effort import resolve_effort, stamp_applied
    from .gateway import _resolve_workspace_root
    from .router_agent import run_router_agent
    from .source_context_worker import materialize_goal

    # Credentials travel only via the approved in-memory binding interface.
    # They are never copied to the request/evidence or ambient environment.
    trace.append("request", {"operation": operation, "source_context": source_context})
    root, error = _resolve_workspace_root(operation.get("root"), repo_root)
    if error:
        raise TraceError()
    rejected = []

    def progress(event):
        try:
            trace.append("progress", event)
            emit({"type": "progress", "event": trace.projection("running")})
        except Exception:
            rejected.append(True)
            raise TraceError() from None

    try:
        result = run_router_agent(
            materialize_goal(operation["goal"], source_context), operation["endpoint"],
            root=str(root), allow_write=operation["allow_write"],
            allow_exec=operation["allow_exec"], max_steps=operation["max_steps"],
            test_cmd=operation.get("test_cmd"), credential_bindings=CredentialBindings(bindings),
            on_event=progress, ledger=TraceLedger(trace), event_errors_fatal=True)
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
