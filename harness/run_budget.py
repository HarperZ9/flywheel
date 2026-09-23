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

The second job is the limit a run keeps hitting, and the success that is
not one. A provider or a CLI reports a limit in its own fields: an HTTP or
API status, an error type, an error or result event, the CLI's own stderr.
The paths read those fields (limit_signal.provider_limit and
provider_body_limit read them by exact value) and hand each limit to
`observe_limit`. Two in a row trip the breaker, because a loop that keeps
retrying into a limit is the runaway this module exists to stop; a clean
provider call in between starts the count again. A limit reported next to
a success, such as a 2xx response whose body is an error or a CLI session
marked success after a limit event, is also a false success, and the run
fails. Tool output and the model's answer are never read for limits: they
are content the model produced or read, and a limit named there is not one
the run hit.

Limits of the check: only the fields a provider or CLI fills are read, and a
limit reported only in prose is missed. A CLI's stderr is read with the
English phrase heuristic in limit_signal. Usage a provider does not report is
not counted, and the report says how many calls reported nothing instead of
estimating them.
"""
from __future__ import annotations

import time

from .gateway_operation import GatewayOperationError
from .limit_signal import provider_body_limit, provider_limit
from .run_budget_contract import DOES_NOT_PROVE, SCHEMA
from .run_budget_executor import BudgetedExecutor, harness_check  # noqa: F401
from .run_budget_usage import reported_cost_micros, reported_tokens

BUDGET_EXHAUSTED = "AGENT_RUN_BUDGET_EXHAUSTED"
FALSE_SUCCESS = "AGENT_FALSE_SUCCESS"

#: Per-run overrides an owner may set, and the range each accepts.
OVERRIDE_BOUNDS = {"max_model_calls": (1, 12), "max_tool_actions": (0, 200),
                   "max_usage_tokens": (1_000, 10_000_000),
                   "max_cost_micros": (10_000, 1_000_000_000)}
#: Defaults when the owner sets nothing. Model calls default to max_steps.
DEFAULTS = {"max_tool_actions": 24, "max_usage_tokens": 200_000,
            "max_cost_micros": 2_000_000}
#: Consecutive counted limit signals before the breaker trips.
LIMIT_SIGNAL_TRIP = 2
#: How many suspected and counted steps a report lists.
_LISTED_STEPS = 32


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


class RunBudget:
    """Counts one run's spend and refuses the step that would exceed it."""

    def __init__(self, limits: dict, *, clock=time.monotonic) -> None:
        self.limits = dict(limits)
        self.used = {"model_calls": 0, "tool_actions": 0,
                     "usage_tokens": 0, "cost_micros": 0}
        self.reporting = {"calls_with_tokens": 0, "calls_without_tokens": 0,
                          "calls_with_cost": 0}
        self.false_success: list[dict] = []
        self.limit_signal_steps: list[dict] = []
        # Runs of the run's own check command: the harness's steps, not the
        # model's, so they are recorded here and never charged.
        self.harness_checks = 0
        # Tokens each CLI message reported as it streamed, by message id.
        self._streamed: dict[str, int] = {}
        self.tripped: str | None = None
        self._armed: str | None = None
        self._consecutive_limit_signals = 0
        self._clock, self._started = clock, clock()

    def charge_model_call(self) -> None:
        self._gate("model_calls")

    def charge_tool_action(self) -> None:
        self._gate("tool_actions")

    def record_harness_check(self) -> None:
        """Record one run of the check command, after a limit armed earlier."""
        self.settle()
        self.harness_checks += 1

    def count_observed(self, name: str) -> None:
        """Count a step another process already started, then stop past the limit.

        A native CLI runs its own tools, so its calls are seen only as they
        stream past. They are counted as spent and the session is stopped at
        the first one over the limit; it cannot be refused beforehand."""
        self.settle()
        self.used[name] += 1
        if self.used[name] > self.limits[name]:
            self._trip(name)

    def record_usage(self, usage=None, *, cost_usd=None, calls: int = 1,
                     cost_calls: int | None = None) -> None:
        """Add one provider report. `calls` is how many model calls its tokens
        cover and `cost_calls` how many its cost covers, when that differs:
        a CLI reports its whole session's cost once, at the end."""
        tokens = reported_tokens(usage)
        if tokens is None:
            self.reporting["calls_without_tokens"] += calls
        else:
            self.reporting["calls_with_tokens"] += calls
            self.used["usage_tokens"] += tokens
        cost = reported_cost_micros(usage, cost_usd)
        if cost is not None:
            self.reporting["calls_with_cost"] += calls if cost_calls is None else cost_calls
            self.used["cost_micros"] += cost
        for name in ("usage_tokens", "cost_micros"):
            if self.used[name] > self.limits[name]:
                self._arm(name)

    def record_streamed_usage(self, message_id, usage) -> None:
        """Count one CLI message's tokens as it streams.

        A message split over several events reports its usage on each, so a
        later report for the same id replaces the earlier one."""
        tokens = reported_tokens(usage)
        if type(message_id) is not str or tokens is None:
            return
        previous = self._streamed.get(message_id)
        self._streamed[message_id] = tokens
        self.used["usage_tokens"] += tokens - (previous or 0)
        self.reporting["calls_with_tokens"] += previous is None
        if self.used["usage_tokens"] > self.limits["usage_tokens"]:
            self._arm("usage_tokens")

    def record_session_usage(self, usage, *, cost_usd=None) -> None:
        """A CLI's end-of-session report, over what its messages streamed.

        The session total adds only the tokens its messages did not already
        report, so nothing is counted twice and nothing streamed is dropped.
        Its tokens cover the model calls no message reported for. Its cost
        covers every call in the session, since no message reports one."""
        tokens, streamed = reported_tokens(usage), sum(self._streamed.values())
        calls = self.unaccounted_calls() or (0 if self._streamed else 1)
        if tokens is not None:
            usage = {"total_tokens": max(0, tokens - streamed)}
        priced = max(1, self.used["model_calls"] - self.reporting["calls_with_cost"])
        self.record_usage(usage, cost_usd=cost_usd, calls=calls, cost_calls=priced)

    def unaccounted_calls(self) -> int:
        """Model calls counted so far that no provider report has covered."""
        return max(0, self.used["model_calls"] - self.reporting["calls_with_tokens"]
                   - self.reporting["calls_without_tokens"])

    def observe_limit(self, source: str, found) -> None:
        """Count a limit the provider or the CLI reported in its own fields.

        `found` is a limit_signal.LimitMatch. Two in a row arm the breaker,
        and the next step is refused."""
        self.limit_signal_steps.append(
            {"tool": str(source)[:64], "signal": found.kind, "match": found.match,
             "action": self.used["tool_actions"]})
        self._consecutive_limit_signals += 1
        if self._consecutive_limit_signals >= self.limits["limit_signals"]:
            self._arm("limit_signals")

    def record_false_success(self, source: str, found) -> None:
        """Name a success the provider or the CLI reported next to a limit."""
        self.false_success.append(
            {"tool": str(source)[:64], "signal": found.kind, "match": found.match,
             "action": self.used["tool_actions"], "counted": True})

    def observe_clean_call(self) -> None:
        """A provider call that reported no limit ends a run of limit signals."""
        self._consecutive_limit_signals = 0

    def observe_provider_response(self, status, body) -> None:
        """Read one provider response's status and error fields for a limit."""
        ok = type(status) is int and 200 <= status < 300
        found = provider_body_limit(body) or (None if ok else provider_limit(status=status))
        if found is None:
            if ok:
                self.observe_clean_call()
            return
        self.observe_limit("provider", found)
        if ok:
            self.record_false_success("provider", found)

    def note_wall_time(self) -> None:
        self.tripped = self.tripped or "wall_time"

    def settle(self) -> None:
        """Stop a run whose last call crossed a limit after it returned."""
        if self._armed is not None:
            self._trip(self._armed)

    def settle_run(self) -> None:
        """Close a run that returned: stop it on a crossed limit, and fail it on
        a success the provider or the CLI reported next to a limit error."""
        self.settle()
        if self.false_success:
            raise GatewayOperationError(FALSE_SUCCESS)

    def settle_failed(self) -> None:
        """Name a crossed limit on a run that already failed for another reason.

        An errored CLI result can report spend past a limit. The run's own
        error stands, and the record still says which limit it crossed."""
        if self.tripped is None and self._armed is not None:
            self.tripped = self._armed

    def wrap_executor(self, executor, *, test_cmd=None):
        return BudgetedExecutor(executor, self, test_cmd=test_cmd)

    def guard_transport(self, transport):
        """Charge each provider request and read the usage it reports."""
        def call(method, url, headers, body, timeout):
            self.charge_model_call()
            try:
                status, obj = transport(method, url, headers, body, timeout)
            except BaseException:
                # A timed-out or refused request can still be billed. It is
                # named as a call that reported nothing, never dropped.
                self.record_usage(None)
                raise
            ok = type(obj) is dict and 200 <= status < 300
            self.observe_provider_response(status, obj)
            # A refused or malformed response still counts as a call that
            # reported no usage, so the report never hides it.
            self.record_usage(obj.get("usage", obj.get("usageMetadata")) if ok else None)
            return status, obj
        return call

    def report(self) -> dict:
        used = dict(self.used)
        used["wall_time_ms"] = max(0, int((self._clock() - self._started) * 1000))
        reporting = dict(self.reporting)
        # A session stopped before its provider reported is named, not guessed.
        reporting["calls_without_tokens"] += self.unaccounted_calls()
        return {"schema": SCHEMA,
                "status": "stopped" if self.tripped else "within_limits",
                "tripped": self.tripped, "limits": dict(self.limits),
                "used": used, "reporting": reporting,
                "false_success_count": len(self.false_success),
                "false_success_steps": [dict(s) for s in self.false_success[:_LISTED_STEPS]],
                "limit_signal_steps": [dict(s) for s in
                                       self.limit_signal_steps[-_LISTED_STEPS:]],
                "harness_checks": self.harness_checks,
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
