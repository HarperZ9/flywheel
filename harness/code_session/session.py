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
from . import context as _context
from .policy import TODO_TOOL_TEXT, WEB_TOOL_TEXT, SessionExecutor, gate_for

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
    compact_budget: int = _context.DEFAULT_BUDGET
    hooks: "object | None" = None
    commands: dict = field(default_factory=dict)

    def set_hooks(self, hooks) -> None:
        """Attach lifecycle hooks; every run is recorded on the ledger."""
        self.hooks = hooks
        hooks.record = lambda run: self.ledger.append(
            "hook", json.dumps(run, sort_keys=True),
            {"event": run["event"], "exit": run["exit"], "blocked": run["blocked"]})

        def pre(name, args):
            out = hooks.fire("PreToolUse", self._hook_base(tool_name=name, tool_input=args),
                             tool=name)
            return out.reason if out.blocked else None

        def post(name, args, result):
            hooks.fire("PostToolUse", self._hook_base(
                tool_name=name, tool_input=args,
                tool_response={"ok": result.ok, "output": result.output[:4000]}), tool=name)
        def permission(name, args):
            out = hooks.fire("PermissionRequest", self._hook_base(tool_name=name, tool_input=args),
                             tool=name)
            return "deny" if out.blocked else ("allow" if out.allowed else None)
        self.executor.pre_tool, self.executor.post_tool = pre, post
        self.executor.permission_hook = permission

    def _hook_base(self, **extra) -> dict:
        return {"session_id": self.session_id, "cwd": self.root, **extra}

    def fire(self, event: str, **extra):
        return self.hooks.fire(event, self._hook_base(**extra)) if self.hooks else None

    def close(self) -> None:
        """Stop background jobs and every MCP server this session started."""
        if self.executor.jobs is not None:
            self.executor.jobs.stop_all()
        for client in self.mcp_clients:
            try:
                client.close()
            except Exception:
                pass
        self.mcp_clients.clear()

    def save_child_ledger(self, index: int, name: str, ledger) -> None:
        """Keep a subagent's ledger beside the session's, when the session is saved."""
        if self.home and self.session_id:
            from .store import sessions_dir
            folder = sessions_dir(self.home) / self.session_id / "subagents"
            folder.mkdir(parents=True, exist_ok=True)
            ledger.save(str(folder / f"{index:03d}-{name}.jsonl"))

    def set_agents(self, agents: dict) -> None:
        from .agents import TASKS_TOOL_TEXT, make_runner, system_text
        self.executor.task_runner = make_runner(self, agents)
        self.agent.system = self.agent.system + "\n\n" + system_text(agents)
        self.agent.system = self.agent.system + chr(10) + TASKS_TOOL_TEXT
        self.ledger.append("agents", json.dumps(sorted(agents)), {"count": len(agents)})

    def persist(self) -> None:
        if self.home:
            from .store import save
            save(self, self.home)

    def __post_init__(self) -> None:
        self.executor.on_decision = self._record_decision
        if self.checkpoints is None:
            self.checkpoints = CheckpointStore(self.root)
        self.executor.before_write = self.checkpoints.snapshot
        from .background import JobTable
        self.executor.jobs = JobTable(self.root, record=lambda kind, data: self.ledger.append(
            "background", json.dumps({"event": kind, **data}, sort_keys=True), {"event": kind}))
        original = self.agent.send

        def counted_send(text):
            if self.hooks is not None and _context.would_fold(self.agent, self.compact_budget):
                self.fire("PreCompact", messages=len(self.agent.history))
            folded = _context.maybe_fold(self.agent, self.compact_budget)
            if folded is not None:
                _context.record_fold(self.ledger, folded)
                self.fire("PostCompact", messages=len(self.agent.history))
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

    def set_skills(self, skills: dict) -> None:
        from .skills import system_text
        self.executor.skills = skills
        text = system_text(skills)
        if text:
            self.agent.system = self.agent.system + "\n\n" + text
        self.ledger.append("skills", json.dumps(sorted(skills)), {"count": len(skills)})

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
        gate = self.fire("UserPromptSubmit", prompt=text)
        if gate is not None and gate.blocked:
            self.ledger.append("blocked", text, {"by": "UserPromptSubmit"})
            return TurnResult(final=f"[blocked by a UserPromptSubmit hook] {gate.reason}",
                              steps=0, verified=self.ledger.verify(),
                              checkpoint=self.ledger.checkpoint(), seconds=0.0)
        self.checkpoints.begin_turn()
        text, attached = _context.expand_mentions(self.root, text)
        if attached:
            self.ledger.append("mention", json.dumps(attached, sort_keys=True),
                               {"files": len(attached)})
        if self.pending_note:
            text, self.pending_note = self.pending_note + "\n\n" + text, ""
        if self.executor.mode == "plan":
            text = PLAN_NOTE + "\n\n" + text
        result = run_agent(self.agent, text, self.executor, self.ledger,
                           max_steps=self.max_steps, test_cmd=self.test_cmd,
                           on_event=self.on_event)
        self.turns += 1
        self.fire("Stop", final=result["final"])
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
    from .background import TOOL_TEXT as BG_TEXT
    if BG_TEXT not in agent.system:
        agent.system = agent.system + chr(10) + BG_TEXT
    if WEB_TOOL_TEXT not in agent.system:
        agent.system = agent.system + "\n" + WEB_TOOL_TEXT
    if TODO_TOOL_TEXT not in agent.system:
        agent.system = agent.system + "\n\n" + TODO_TOOL_TEXT
    return CodeSession(agent=agent, executor=executor, root=root, max_steps=max_steps,
                       test_cmd=test_cmd, on_event=on_event)
