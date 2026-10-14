"""session.py -- one interactive coding session: agent, tools, ledger, turns.

A session keeps three things across turns: the model conversation (the
agent's history), the tool executor with its permission mode, and one
hash-chained SessionLedger that records every user turn, model reply, tool
call, tool result and permission decision. Each user turn runs the existing
gated tool loop (harness.local_loop.run_agent) to its final answer, so a turn
can read, edit and test, and the next turn starts from what the last one did.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from harness.local_loop import run_agent
from harness.local_session import SessionLedger

from . import instructions as _instructions
from .backends import describe
from .policy import SessionExecutor, gate_for

DEFAULT_MAX_STEPS = 25


@dataclass
class TurnResult:
    final: str
    steps: int
    verified: bool
    checkpoint: str
    seconds: float
    tests_pass: "bool | None" = None


@dataclass
class CodeSession:
    agent: object
    executor: SessionExecutor
    root: str
    ledger: SessionLedger = field(default_factory=SessionLedger)
    max_steps: int = DEFAULT_MAX_STEPS
    test_cmd: "str | None" = None
    on_event: "Callable[[dict], None] | None" = None
    loaded: list = field(default_factory=list)
    turns: int = 0

    def __post_init__(self) -> None:
        self.executor.on_decision = self._record_decision

    def _record_decision(self, decision: dict) -> None:
        self.ledger.append("approval", json.dumps(decision, sort_keys=True), decision)

    def load_instructions(self, home: "str | None") -> list:
        """Fold project instruction files into the system prompt, once."""
        self.loaded = _instructions.load_instructions(self.root, home)
        addendum = _instructions.system_addendum(self.loaded, self.root)
        if addendum:
            self.agent.system = f"{self.agent.system}\n\n{addendum}"
        self.ledger.append("instructions", json.dumps([i.record() for i in self.loaded]),
                           {"count": len(self.loaded)})
        return self.loaded

    def set_mode(self, mode: str) -> None:
        self.executor.set_mode(mode)
        self.ledger.append("mode", mode, {"mode": mode})

    def status(self) -> dict:
        return {"root": self.root, "mode": self.executor.mode,
                "backend": describe(self.agent.live_backend()),
                "turns": self.turns, "ledger_entries": len(self.ledger.entries),
                "checkpoint": self.ledger.checkpoint(),
                "chain_ok": self.ledger.verify(),
                "instructions": [i.path for i in self.loaded]}

    def clear(self) -> None:
        """Forget the conversation; the ledger keeps the record of it."""
        self.agent.history.clear()
        self.ledger.append("clear", "conversation cleared", {})

    def turn(self, text: str) -> TurnResult:
        """Run one user request through the gated tool loop to a final answer."""
        started = time.monotonic()
        result = run_agent(self.agent, text, self.executor, self.ledger,
                           max_steps=self.max_steps, test_cmd=self.test_cmd,
                           on_event=self.on_event)
        self.turns += 1
        return TurnResult(final=result["final"], steps=result["steps"],
                          verified=bool(result.get("verified")),
                          checkpoint=result["checkpoint"],
                          seconds=time.monotonic() - started,
                          tests_pass=result.get("tests_pass"))


def new_session(agent, root: str, *, mode: str = "ask", approver=None,
                runner=None, max_steps: int = DEFAULT_MAX_STEPS,
                test_cmd: "str | None" = None, on_event=None) -> CodeSession:
    """A session over `root` with the executor built for `mode`."""
    executor = SessionExecutor(root=root, gate=gate_for(mode), runner=runner, mode=mode)
    if approver is not None:
        executor.approver = approver
    return CodeSession(agent=agent, executor=executor, root=root, max_steps=max_steps,
                       test_cmd=test_cmd, on_event=on_event)
