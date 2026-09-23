"""Real-router execution with private evidence and metadata-only IPC."""
from __future__ import annotations

from pathlib import Path

from .credential_handles import CredentialBindings
from .gateway_agent_trace import AgentTrace, TraceError, TraceLedger


def run_private_agent(operation: dict, bindings: dict, repo_root: Path,
                      trace: AgentTrace, source_context, emit, *, binding=None, deadline=None) -> dict:
    from .effort import resolve_effort, stamp_applied
    from .gateway_agent_binding import validate_agent_binding
    from .gateway_agent_workspace import pinned_workspace
    from .gateway_operation import canonicalize_operation, materialize_agent_attachment, GatewayOperationError
    from .run_budget import RunBudget, resolve_limits

    # Credentials travel only via the approved in-memory binding interface.
    # They are never copied to the request/evidence or ambient environment.
    if binding is None or type(deadline) not in (int, float):
        raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    validate_agent_binding(binding, canonicalize_operation("agent.run", operation))
    trace.append("request", {"operation": operation, "source_context": source_context, "execution_binding": binding})
    execution = materialize_agent_attachment(operation)
    ledger = TraceLedger(trace)
    budget = RunBudget(resolve_limits(operation))
    rejected, cli_events, completion = [], [], {}

    def progress(event):
        try:
            trace.append("progress", event)
            emit({"type": "progress", "event": trace.projection("running")})
        except Exception:
            rejected.append(True)
            raise TraceError() from None
        if type(event) is dict and str(event.get("type", "")).startswith("cli_tool"):
            cli_events.append(event)

    try:
        with pinned_workspace(binding["workspace"]) as root:
            result = _run_checked(root, source_context, binding, bindings, ledger, trace,
                                  deadline, progress, execution, budget, cli_events, completion)
        if rejected:
            raise TraceError()
        if operation.get("effort"):
            result["effort"] = stamp_applied(resolve_effort(operation["effort"]),
                max_steps_applied=operation["max_steps"], n_candidates_applied=False)
        result["run_budget"], result["completion"] = budget.report(), completion
        trace.append("result", result)
        return trace.projection("completed", runtime=result.get("environment", {}))
    except Exception as exc:
        _record_failure(trace, exc, budget, completion)
        raise


def _run_checked(root, source_context, binding, bindings, ledger, trace, deadline,
                 progress, execution, budget, cli_events, completion) -> dict:
    """Run under the budget and sort the deliverables while the workspace is pinned.

    The split is computed here, before the pin is released, on the failure path
    too, so the files a stopped run wrote are rechecked like those of a finished
    run. `completion` is filled in place for the caller's failure record."""
    import time
    from .gateway_operation import GatewayOperationError
    from .source_context_worker import materialize_goal
    try:
        goal = materialize_goal(execution["goal"], source_context)
        result = _run_bound_path(goal, binding, bindings, root, ledger, trace,
                                 deadline, progress, execution, budget)
        _settle_budget(result, budget)
        if time.monotonic() >= deadline:
            raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    except Exception as exc:
        completion.update(_completion(ledger, None, root, cli_events, exc))
        raise
    completion.update(_completion(ledger, result, root, cli_events))
    return result


def _run_bound_path(goal, binding, bindings, root, ledger, trace, deadline,
                    progress, execution, budget) -> dict:
    """Dispatch to the one execution path the binding names, under the budget."""
    if binding.get('execution_mode') == 'native_cli_session':
        from .gateway_cli_execution import run_cli_session
        return run_cli_session(goal, binding, root, deadline, progress,
            state_root=trace.root, state_identity=trace.identity, budget=budget)
    if binding.get("tool_protocol", {}).get("protocol") == "native":
        from .gateway_agent_native_tools import run_native_tool_agent
        return run_native_tool_agent(goal, binding,
            CredentialBindings(bindings), root, ledger, deadline,
            on_event=progress, test_cmd=execution.get("test_cmd"), budget=budget)
    from .gateway_agent_mcp_admission import open_mcp_runtime
    from .gateway_agent_proposer import BoundAgentProposer
    from .router_agent import run_router_agent
    bound_credentials = CredentialBindings(bindings)
    proposer = BoundAgentProposer(binding, bound_credentials, ledger, deadline, budget=budget)
    with open_mcp_runtime(binding.get("mcp_admission"),
                          credentials=bound_credentials, root=root,
                          on_event=progress,
                          deadline=deadline) as mcp_runtime:
        return run_router_agent(
            goal, binding["endpoint"]["name"], root=str(root),
            allow_write=binding["capabilities"]["allow_write"],
            allow_exec=binding["capabilities"]["allow_exec"], max_steps=binding["budget"]["max_steps"],
            allow_mcp=mcp_runtime["allow_mcp"], external=mcp_runtime["external"],
            model=binding["model"]["model_id"], max_tokens=binding["budget"]["max_tokens"],
            temperature=binding["sampling"]["temperature"], seed=binding["sampling"]["router_seed"],
            proposer=proposer, test_cmd=execution.get("test_cmd"),
            credential_bindings=bound_credentials,
            on_event=progress, ledger=ledger, event_errors_fatal=True, budget=budget)


def _settle_budget(result: dict, budget) -> None:
    """Stop a run whose last step crossed a limit, or that reported a false success.

    A provider or a CLI can report success next to a limit in its own fields:
    a 2xx response whose body carries a completion and a rate-limit error, a
    CLI session marked success after a limit event, a CLI that exits 0 with a
    limit error on its stderr. The paths record those as they read them, and
    the run fails here. A 2xx body that is only a limit error holds no
    completion, so its call fails first, with the path's own code. The final
    answer is model prose and is never read for a limit, on any path, so an
    answer about 429 handling completes."""
    budget.settle_run()


def _completion(ledger, result, root, cli_events, exc=None) -> dict:
    """The verified, claimed and failed split for this run, never raising.

    A defect in the check must not replace the run's own outcome, so it is
    recorded as an unavailable report with its reason instead."""
    from .gateway_agent_failures import failure_reason
    from .run_completion import SCHEMA, completion_report
    try:
        return completion_report(ledger.entries, result, root, cli_events=cli_events,
                                 failure=None if exc is None else failure_reason(exc))
    except Exception as error:  # recorded, never silent: the reader sees why
        return {"schema": SCHEMA, "verdict": "unavailable",
                "reason": f"COMPLETION_CHECK_FAILED:{type(error).__name__}"}


def _record_failure(trace, exc, budget, completion=None) -> None:
    """Write why the run stopped, with the budget and completion as they stood.

    A limit the run crossed before it failed is settled first, so the record
    never says within limits next to numbers over them."""
    budget.settle_failed()
    if getattr(exc, "code", None) == "OPERATION_DEADLINE_EXCEEDED":
        budget.note_wall_time()
    payload = {"error_type": type(exc).__name__, "message": str(exc),
               "run_budget": budget.report()}
    if completion:
        payload["completion"] = completion
    try:
        trace.append("failure", payload)
    except Exception:
        pass  # rejected credentials/custody never enter the diagnostic record



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
    """The projection of a run the worker did not close itself.

    When the deadline stopped the process tree mid-step, the worker wrote no
    budget record, so the gateway writes the wall-time stop the trace supports
    before it projects (run_budget_deadline)."""
    trace = AgentTrace(state_root, owner, journey, operation)
    records = trace.read()
    if not records:
        return None
    if state == "failed" and reason == "OPERATION_DEADLINE_EXCEEDED":
        from .run_budget_deadline import record_deadline_stop
        try:
            record_deadline_stop(trace, records)
        except (TraceError, KeyError, StopIteration, ValueError):
            # The trace refused the record or has no request to read limits
            # from. The run still closes, and the card says the time limit was
            # reached before a budget record was written.
            trace = AgentTrace(state_root, owner, journey, operation)
            trace.read()
    return trace.projection(state, reason=reason)
