"""run_budget_executor.py -- the run budget's hook on tool actions.

BudgetedExecutor charges each of the model's tool actions to the run budget
before it runs. The run's own check command is the harness's step, not the
model's: run inside `harness_check`, it is recorded in the budget record as a
harness check and is not charged, so a run whose `max_tool_actions` is 0 can
still be checked. A run of the same command that the model asks for is the
model's action and is charged like any other.

No output is read for a limit here. A tool's output is content the model
produced or read, and run_budget reads limits only from the provider's and
the CLI's own fields.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext


class BudgetedExecutor:
    """A tool executor that charges each model action before it runs.

    Everything else passes through to the wrapped executor, so receipt
    chains, the byte witness and the workspace root keep working."""

    def __init__(self, inner, budget, *, test_cmd=None) -> None:
        self._inner, self._budget, self._test_cmd = inner, budget, test_cmd
        self._harness = False

    @contextmanager
    def harness_check(self):
        """Run the next call as the harness's own check command."""
        self._harness = True
        try:
            yield
        finally:
            self._harness = False

    def execute(self, name, args, *extra, **kwargs):
        if self._harness:
            self._harness = False
            self._budget.record_harness_check()
        else:
            self._budget.charge_tool_action()
        return self._inner.execute(name, args, *extra, **kwargs)

    def __getattr__(self, attr):
        return getattr(self._inner, attr)


def harness_check(executor):
    """The context in which `executor` runs the harness's own check command.

    It finds the budgeted executor under any wrappers (the check guard wraps
    it) through their own `_inner` attribute, never through a delegating
    lookup. With no budget on the executor it changes nothing."""
    target = executor
    for _ in range(8):
        if isinstance(target, BudgetedExecutor):
            return target.harness_check()
        target = vars(target).get("_inner") if hasattr(target, "__dict__") else None
        if target is None:
            break
    return nullcontext()
