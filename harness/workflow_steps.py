"""workflow_steps.py -- one workflow stage, run under the workflow's run budget.

workflow.run, the /api/workflow route and plan.run drive the router agent
once per stage through workflows.run_workflow. They carry the budget and the
settle path agent.run uses:

- one RunBudget covers the whole workflow run, with agent.run's defaults and
  a model-call limit that is the sum of the stages' step budgets;
- every stage's model calls and tool actions are charged to it, and the
  provider's own status and error fields are read for a limit;
- each stage is settled when it returns (RunBudget.settle_run), so a crossed
  limit or a false success stops the workflow there;
- each stage summary carries the budget record as it stood, so the chained
  receipt shows what the run spent and why it stopped.

A budget stop is written into the receipt as a STOPPED stage, including on the
authorized routes, where any other stage failure aborts the whole run.
"""
from __future__ import annotations

from .endpoint_registry import ProviderPermissionError
from .gateway_operation import GatewayOperationError
from .run_budget import BUDGET_EXHAUSTED, FALSE_SUCCESS, RunBudget, resolve_limits

#: The verify stage's step budget: run the check, report the outcome.
VERIFY_MAX_STEPS = 2


def workflow_budget(steps: list) -> RunBudget:
    """One budget for a workflow run: agent.run's defaults over every stage."""
    total = sum(VERIFY_MAX_STEPS if step["kind"] == "verify" else step.get("max_steps", 6)
                for step in steps)
    return RunBudget(resolve_limits({"max_steps": max(1, total)}))


def step_summary(name: str, kind: str, status: str, result: dict | None,
                 note: str = "", budget: RunBudget | None = None) -> dict:
    s = {"name": name, "kind": kind, "status": status}
    if note:
        s["note"] = note
    if result:
        final = str(result.get("final", ""))
        s["excerpt"] = final[:400]
        s["steps"] = result.get("steps")
        s["checkpoint"] = result.get("checkpoint")
        s["ledger_verified"] = result.get("verified")
        integrity = result.get("integrity")
        if isinstance(integrity, dict):
            s["integrity_clean"] = integrity.get("clean")
        if "tests_pass_trusted" in result:
            s["tests_pass_trusted"] = result["tests_pass_trusted"]
    if budget is not None:
        s["run_budget"] = budget.report()
    return s


def fixed_if_authorized(authorized: bool, exc: Exception) -> None:
    if not authorized:
        return
    if isinstance(exc, ProviderPermissionError):
        raise ProviderPermissionError() from None
    raise RuntimeError("authorized external action failed") from None


def run_stage(runner, budget: RunBudget, goal: str, endpoint: str, **kwargs):
    """Run one stage under the budget and settle it, as agent.run does.

    Returns (result, stop). `stop` is None, or the stop code with the limit
    that tripped, when the budget stopped the stage."""
    try:
        result = runner(goal, endpoint, budget=budget, **kwargs)
        budget.settle_run()
    except GatewayOperationError as exc:
        if exc.code not in (BUDGET_EXHAUSTED, FALSE_SUCCESS):
            raise
        budget.settle_failed()
        limit = getattr(exc, "limit", None)
        return None, f"{exc.code}: {limit}" if limit else exc.code
    return result, None


def verify_step(step, endpoint, runner, budget, *, root, allow_write, test_cmd, proposer,
                credential_bindings, authorized):
    try:
        result, stop = run_stage(
            runner, budget, "Run the test command and report the outcome honestly.",
            endpoint, root=root, allow_exec=True, allow_write=allow_write,
            max_steps=VERIFY_MAX_STEPS, test_cmd=test_cmd, proposer=proposer,
            credential_bindings=credential_bindings)
    except Exception as exc:
        budget.settle_failed()
        fixed_if_authorized(authorized, exc)
        return step_summary(step["name"], "verify", "ERROR", None,
                            note=f"{type(exc).__name__}: {exc}", budget=budget), "FAILED"
    if stop is not None:
        return step_summary(step["name"], "verify", "STOPPED", None, note=stop,
                            budget=budget), "FAILED"
    status = "VERIFIED" if result.get("tests_pass_trusted") else "FAILED"
    return step_summary(step["name"], "verify", status, result, budget=budget), status


def agent_step(step, goal, prev, endpoint, runner, budget, *, root, allow_write,
               allow_exec, allow_mcp, system, proposer, credential_bindings, authorized):
    step_goal = step["goal"].format(goal=goal, prev=prev)
    if system:
        step_goal = f"{system}\n\n{step_goal}"
    try:
        result, stop = run_stage(
            runner, budget, step_goal, endpoint, root=root, allow_write=allow_write,
            allow_exec=allow_exec, allow_mcp=allow_mcp, max_steps=step.get("max_steps", 6),
            proposer=proposer, credential_bindings=credential_bindings)
    except Exception as exc:
        budget.settle_failed()
        fixed_if_authorized(authorized, exc)
        return step_summary(step["name"], "agent", "ERROR", None,
                            note=f"{type(exc).__name__}: {exc}", budget=budget), prev, "FAILED", True
    if stop is not None:
        return step_summary(step["name"], "agent", "STOPPED", None, note=stop,
                            budget=budget), prev, "FAILED", True
    summary = step_summary(step["name"], "agent", "DONE", result, budget=budget)
    reasons = []
    if result.get("verified") is False:
        reasons.append("ledger did not verify")
    if summary.get("integrity_clean") is False:
        reasons.append("trajectory integrity dirty")
    if reasons:
        summary["status"] = "FAILED"
        summary["note"] = "; ".join(reasons)
        return summary, str(result.get("final", "")), "FAILED", True
    return summary, str(result.get("final", "")), None, False
