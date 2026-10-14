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
from .checkpoints import CheckpointStore
from .policy import TODO_TOOL_TEXT, SessionExecutor, gate_for

DEFAULT_MAX_STEPS = 25
PLAN_NOTE = ("[plan mode: you can read and search but not write files or run commands. "
             "Investigate, then answer with a numbered plan of the changes you would make "
             "and how you would check them.]")


def new_usage() -> dict:
    return {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "uncounted_calls": 0}


def add_usage(total: dict, resp: dict) -> None:
    """Add one model call's provider-reported tokens; a call without them is counted
    as uncounted, never estimated."""
    total["model_calls"] += 1
    counted = resp.get("x_token_usage") if isinstance(resp, dict) else None
    if counted:
        total["input_tokens"] += int(counted.get("input_tokens", 0))
        total["output_tokens"] += int(counted.get("output_tokens", 0))
    else:
        total["uncounted_calls"] += 1


@dataclass
class TurnResult:
    final: str
    steps: int
    verified: bool
    checkpoint: str
    seconds: float
    tests_pass: "bool | None" = None
    usage: dict = field(default_factory=dict)


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
    session_id: str = ""
    checkpoints: "CheckpointStore | None" = None
    pending_note: str = ""
    home: str = ""                  # set to save after every turn and undo
    usage: dict = field(default_factory=lambda: new_usage())
    mcp_clients: list = field(default_factory=list)

    def close(self) -> None:
        """Stop every MCP server this session started."""
        for client in self.mcp_clients:
            try:
                client.close()
            except Exception:
                pass
        self.mcp_clients.clear()

    def persist(self) -> None:
        if self.home:
            from .store import save
            save(self, self.home)

    def __post_init__(self) -> None:
        self.executor.on_decision = self._record_decision
        if self.checkpoints is None:
            self.checkpoints = CheckpointStore(self.root)
        self.executor.before_write = self.checkpoints.snapshot
        original = self.agent.send

        def counted_send(text):
            resp = original(text)
            add_usage(self.usage, resp)
            return resp
        self.agent.send = counted_send

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

    def set_rules(self, rules) -> None:
        self.executor.rules = rules
        self.ledger.append("rules", json.dumps({"sources": rules.sources, "allow": rules.allow,
                                                "deny": rules.deny}, sort_keys=True),
                           {"allow": len(rules.allow), "deny": len(rules.deny)})

    def set_mode(self, mode: str) -> None:
        self.executor.set_mode(mode)
        self.ledger.append("mode", mode, {"mode": mode})

    def status(self) -> dict:
        return {"root": self.root, "mode": self.executor.mode,
                "backend": describe(self.agent.live_backend()),
                "turns": self.turns, "ledger_entries": len(self.ledger.entries),
                "checkpoint": self.ledger.checkpoint(),
                "chain_ok": self.ledger.verify(),
                "instructions": [i.path for i in self.loaded], "usage": dict(self.usage)}

    def clear(self) -> None:
        """Forget the conversation; the ledger keeps the record of it."""
        self.agent.history.clear()
        self.ledger.append("clear", "conversation cleared", {})

    def undo(self) -> "list[dict] | None":
        """Put back the files the newest changing turn wrote; tell the model next turn."""
        restored = self.checkpoints.undo()
        if restored is None:
            return None
        self.ledger.append("undo", json.dumps(restored, sort_keys=True),
                           {"files": len(restored)})
        paths = ", ".join(r["path"] for r in restored)
        self.persist()
        self.pending_note = (f"[note: the user undid your previous file changes; these "
                             f"files are back as they were before that turn: {paths}]")
        return restored

    def turn(self, text: str) -> TurnResult:
        """Run one user request through the gated tool loop to a final answer."""
        started = time.monotonic()
        before = dict(self.usage)
        self.checkpoints.begin_turn()
        if self.pending_note:
            text, self.pending_note = self.pending_note + "\n\n" + text, ""
        if self.executor.mode == "plan":
            text = PLAN_NOTE + "\n\n" + text
        result = run_agent(self.agent, text, self.executor, self.ledger,
                           max_steps=self.max_steps, test_cmd=self.test_cmd,
                           on_event=self.on_event)
        self.turns += 1
        self.persist()
        return TurnResult(final=result["final"], steps=result["steps"],
                          verified=bool(result.get("verified")),
                          checkpoint=result["checkpoint"],
                          seconds=time.monotonic() - started,
                          tests_pass=result.get("tests_pass"),
                          usage={k: self.usage[k] - before.get(k, 0) for k in self.usage})


def new_session(agent, root: str, *, mode: str = "ask", approver=None,
                runner=None, max_steps: int = DEFAULT_MAX_STEPS,
                test_cmd: "str | None" = None, on_event=None) -> CodeSession:
    """A session over `root` with the executor built for `mode`."""
    executor = SessionExecutor(root=root, gate=gate_for(mode), runner=runner, mode=mode)
    if approver is not None:
        executor.approver = approver
    if TODO_TOOL_TEXT not in agent.system:
        agent.system = agent.system + "\n\n" + TODO_TOOL_TEXT
    return CodeSession(agent=agent, executor=executor, root=root, max_steps=max_steps,
                       test_cmd=test_cmd, on_event=on_event)
