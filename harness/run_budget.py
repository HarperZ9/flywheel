"""run_budget.py -- a hard circuit breaker on one agent run.

An unattended run spends things its owner pays for or waits on: model calls,
tool actions, provider-reported tokens and, where a provider reports it,
money. Wall time is the fifth. It already has an owner, the aggregate
deadline over the worker process tree (gateway_agent_deadline), so this
module records it and does not enforce it a second time.

The breaker trips at a step boundary. A model call or tool action that would
go past its limit is refused before it starts. Tokens and cost are known only
after a call returns, so crossing either limit arms the breaker and the next
step is refused. When the crossing call was the last one, `settle()` still
stops the run. Either way the run fails with AGENT_RUN_BUDGET_EXHAUSTED and
the report names the limit that tripped.

The second job is the success that is not one. A command can exit 0 while its
output says the account hit a rate limit, ran out of quota or failed to sign
in. `limit_signal` (in limit_signal.py) reads for that signature and the
step is recorded as failed. Two limit signals in a row trip the breaker, because a loop that
keeps retrying into a limit is the runaway this module exists to stop.

Limits of the check: `limit_signal` is a phrase heuristic. It misses an error
worded another way, and it can flag a short output that quotes one of the
phrases. Usage a provider does not report is not counted, and the report says
how many calls reported nothing instead of estimating them.
"""
from __future__ import annotations

import time
from dataclasses import replace

from .gateway_operation import GatewayOperationError
from .limit_signal import limit_signal
from .run_budget_contract import DOES_NOT_PROVE, SCHEMA

BUDGET_EXHAUSTED = "AGENT_RUN_BUDGET_EXHAUSTED"
FALSE_SUCCESS = "AGENT_FALSE_SUCCESS"

#: Per-run overrides an owner may set, and the range each accepts.
OVERRIDE_BOUNDS = {"max_model_calls": (1, 12), "max_tool_actions": (0, 200),
                   "max_usage_tokens": (1_000, 10_000_000),
                   "max_cost_micros": (10_000, 1_000_000_000)}
#: Defaults when the owner sets nothing. Model calls default to max_steps.
DEFAULTS = {"max_tool_actions": 24, "max_usage_tokens": 200_000,
            "max_cost_micros": 2_000_000}
#: Consecutive steps reporting a limit before the breaker trips.
LIMIT_SIGNAL_TRIP = 2

# Tools whose output is file content or a listing. Scanning it would flag a
# file that merely mentions a rate limit, so only actions are scanned.
_CONTENT_TOOLS = frozenset({
    "read_file", "list_dir", "grep", "glob", "repo_map", "write_file",
    "edit_file", "apply_patch",
    "Read", "Glob", "Grep", "LS", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "TodoWrite"})


class RunBudgetExceeded(GatewayOperationError):
    def __init__(self, limit: str) -> None:
        super().__init__(BUDGET_EXHAUSTED)
        self.limit = limit


def validate_run_budget_request(value) -> None:
    """Refuse an override that names no limit, an unknown one, or a bad value."""
    if (type(value) is not dict or not value
            or any(key not in OVERRIDE_BOUNDS for key in value)):
        raise ValueError("run_budget names known limits only")
    for key, item in value.items():
        low, high = OVERRIDE_BOUNDS[key]
        if type(item) is not int or not low <= item <= high:
            raise ValueError(f"run_budget.{key} is an integer in [{low}, {high}]")


def resolve_limits(operation: dict) -> dict:
    """The limits one run is held to: owner overrides over the defaults."""
    override = operation.get("run_budget")
    if override is not None:
        validate_run_budget_request(override)
    chosen = {**DEFAULTS, "max_model_calls": operation["max_steps"], **(override or {})}
    return {"model_calls": chosen["max_model_calls"],
            "tool_actions": chosen["max_tool_actions"],
            "usage_tokens": chosen["max_usage_tokens"],
            "cost_micros": chosen["max_cost_micros"],
            "limit_signals": LIMIT_SIGNAL_TRIP,
            "wall_time_ms": int(operation.get("timeout_s", 300)) * 1000}


def _reported_tokens(usage) -> int | None:
    if type(usage) is not dict:
        return None
    total = usage.get("total_tokens", usage.get("totalTokenCount"))
    if type(total) is int and total >= 0:
        return total
    parts = [usage.get(k) for k in ("prompt_tokens", "input_tokens", "promptTokenCount",
                                    "completion_tokens", "output_tokens",
                                    "candidatesTokenCount")]
    counted = [p for p in parts if type(p) is int and p >= 0]
    return sum(counted) if counted else None


def _reported_cost_micros(usage, cost_usd) -> int | None:
    value = cost_usd if cost_usd is not None else (
        usage.get("cost") if type(usage) is dict else None)
    if type(value) in (int, float) and value >= 0 and value == value:
        return int(round(value * 1_000_000))
    return None


class RunBudget:
    """Counts one run's spend and refuses the step that would exceed it."""

    def __init__(self, limits: dict, *, clock=time.monotonic) -> None:
        self.limits = dict(limits)
        self.used = {"model_calls": 0, "tool_actions": 0,
                     "usage_tokens": 0, "cost_micros": 0}
        self.reporting = {"calls_with_tokens": 0, "calls_without_tokens": 0,
                          "calls_with_cost": 0}
        self.false_success: list[dict] = []
        self.tripped: str | None = None
        self._armed: str | None = None
        self._streak = 0
        self._clock, self._started = clock, clock()

    def charge_model_call(self) -> None:
        self._gate("model_calls")

    def charge_tool_action(self) -> None:
        self._gate("tool_actions")

    def count_observed(self, name: str) -> None:
        """Count a step another process already started, then stop past the limit.

        A native CLI runs its own tools, so its calls are seen only as they
        stream past. They are counted as spent and the session is stopped at
        the first one over the limit; it cannot be refused beforehand."""
        self.settle()
        self.used[name] += 1
        if self.used[name] > self.limits[name]:
            self._trip(name)

    def record_usage(self, usage=None, *, cost_usd=None) -> None:
        tokens = _reported_tokens(usage)
        if tokens is None:
            self.reporting["calls_without_tokens"] += 1
        else:
            self.reporting["calls_with_tokens"] += 1
            self.used["usage_tokens"] += tokens
        cost = _reported_cost_micros(usage, cost_usd)
        if cost is not None:
            self.reporting["calls_with_cost"] += 1
            self.used["cost_micros"] += cost
        for name in ("usage_tokens", "cost_micros"):
            if self.used[name] > self.limits[name]:
                self._arm(name)

    def observe_step(self, tool: str, ok: bool, output) -> str | None:
        """Read one action's output. Returns the limit it reports, if any."""
        if tool in _CONTENT_TOOLS:
            return None
        signal = limit_signal(output)
        if signal is None:
            self._streak = 0
            return None
        self._streak += 1
        if ok:
            self.false_success.append({"tool": str(tool)[:64], "signal": signal,
                                       "action": self.used["tool_actions"]})
        if self._streak >= self.limits["limit_signals"]:
            self._arm("limit_signals")
        return signal

    def note_wall_time(self) -> None:
        self.tripped = self.tripped or "wall_time"

    def settle(self) -> None:
        """Stop a run whose last call crossed a limit after it returned."""
        if self._armed is not None:
            self._trip(self._armed)

    def wrap_executor(self, executor):
        return BudgetedExecutor(executor, self)

    def guard_transport(self, transport):
        """Charge each provider request and read the usage it reports."""
        def call(method, url, headers, body, timeout):
            self.charge_model_call()
            status, obj = transport(method, url, headers, body, timeout)
            if type(obj) is dict and 200 <= status < 300:
                self.record_usage(obj.get("usage", obj.get("usageMetadata")))
            return status, obj
        return call

    def report(self) -> dict:
        used = dict(self.used)
        used["wall_time_ms"] = max(0, int((self._clock() - self._started) * 1000))
        return {"schema": SCHEMA,
                "status": "stopped" if self.tripped else "within_limits",
                "tripped": self.tripped, "limits": dict(self.limits),
                "used": used, "reporting": dict(self.reporting),
                "false_success_count": len(self.false_success),
                "false_success_steps": [dict(s) for s in self.false_success[:32]],
                "does_not_prove": list(DOES_NOT_PROVE)}

    def _gate(self, name: str) -> None:
        self.settle()
        if self.used[name] >= self.limits[name]:
            self._trip(name)
        self.used[name] += 1

    def _arm(self, name: str) -> None:
        if self._armed is None:
            self._armed = name

    def _trip(self, name: str) -> None:
        self.tripped = name
        raise RunBudgetExceeded(name)


_FALSE_SUCCESS_NOTE = ("[flywheel] the step exited 0 but its output reports a "
                       "{signal} error; it is recorded as failed.\n")


class BudgetedExecutor:
    """A tool executor that charges each action before it runs.

    Everything else passes through to the wrapped executor, so receipt
    chains, the byte witness and the workspace root keep working."""

    def __init__(self, inner, budget: RunBudget) -> None:
        self._inner, self._budget = inner, budget

    def execute(self, name, args, *extra, **kwargs):
        self._budget.charge_tool_action()
        result = self._inner.execute(name, args, *extra, **kwargs)
        signal = self._budget.observe_step(name, result.ok, result.output)
        if signal is not None and result.ok:
            return replace(result, ok=False, output=_FALSE_SUCCESS_NOTE.format(
                signal=signal.replace("_", " ")) + result.output)
        return result

    def __getattr__(self, attr):
        return getattr(self._inner, attr)
