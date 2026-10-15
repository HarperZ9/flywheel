"""agents.py -- subagents for a coding session, and the `task` tool that runs them.

An agent is a Markdown file in `.flywheel/agents/`, `.claude/agents/` (read for
compatibility) or `agents/` in the Flywheel home:

    ---
    name: reviewer
    description: reviews a diff for bugs and missing tests
    tools: read_file, grep, glob, list_dir
    model: claude-sonnet-5
    ---
    You review changes. Report bugs with file and line...

The body is the agent's system prompt. `tools` limits what it may call (every
tool when absent); `model` picks a model on the same backend. One agent is built
in: `explore`, which can only read and search.

`TOOL task {"agent": "reviewer", "prompt": "..."}` runs the agent on a fresh
conversation with its own hash-chained ledger and returns its final answer. The
child works under the parent's permission mode, rules and approver, so a
subagent can never do what the session could not; it cannot start subagents of
its own. The parent's ledger records the child's name, its ledger head and
whether the child's chain verifies, and a saved session keeps the child ledger
beside its own.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRS = (Path(".flywheel") / "agents", Path(".claude") / "agents")
READ_ONLY = ("read_file", "list_dir", "repo_map", "grep", "glob")
ALL_TOOLS = READ_ONLY + ("write_file", "edit_file", "apply_patch", "run", "web_fetch", "web_search",
                         "todo", "skill")
TASK_TOOL_TEXT = ('TOOL task {"agent": "<name>", "prompt": "<what to do>"}  runs a subagent '
                  "on a fresh conversation and returns its answer.")


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    system: str
    tools: "tuple | None"
    model: str
    source: str


BUILTIN = {"explore": AgentSpec(
    "explore", "reads and searches the project to answer a question; changes nothing",
    "You explore a code base to answer one question. Read and search, then answer "
    "with file paths and line references. You cannot change files or run commands.",
    READ_ONLY, "", "built-in")}


def _parse(path: Path) -> "AgentSpec | None":
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].splitlines():
                key, sep, value = line.partition(":")
                if sep:
                    meta[key.strip()] = value.strip().strip('"').strip("'")
            body = raw[end + 4:].lstrip("\n")
    name = meta.get("name") or path.stem
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        return None
    tools = tuple(t.strip() for t in meta["tools"].split(",") if t.strip()) \
        if meta.get("tools") else None
    return AgentSpec(name, meta.get("description", ""), body.strip(), tools,
                     meta.get("model", ""), str(path))


def load_agents(root: str, home: "str | None") -> dict:
    found = dict(BUILTIN)
    from .plugins import plugin_roots
    folders = [Path(root) / d for d in PROJECT_DIRS] + ([Path(home) / "agents"] if home else [])
    folders += [r / "agents" for r in plugin_roots(home)]
    for folder in folders:
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                spec = _parse(path)
            except OSError:
                continue
            if spec is not None and spec.name not in found:
                found[spec.name] = spec
    return found


def system_text(agents: dict) -> str:
    lines = [TASK_TOOL_TEXT, "Subagents:"]
    lines += [f"- {a.name}: {a.description[:160]}" for a in agents.values()]
    return "\n".join(lines)


def _child_agent(parent_agent, spec: AgentSpec):
    from .backends import build_agent
    backends = list(parent_agent.backends)
    if spec.model:
        backends = [copy.copy(b) for b in backends]
        for b in backends:
            if hasattr(b, "model"):
                b.model = spec.model
    return build_agent(backends, prefer=parent_agent.prefer,
                       max_tokens=parent_agent.max_tokens, system=spec.system or
                       "You are a focused subagent. Do the task and answer briefly.")


def make_runner(session, agents: dict):
    """The callable the parent executor's `task` tool uses."""
    from .session import new_session
    counter = {"n": 0}

    def run(args: dict) -> "tuple[bool, str]":
        spec = agents.get(str(args.get("agent", "")))
        prompt = str(args.get("prompt", "")).strip()
        if spec is None or not prompt:
            known = ", ".join(sorted(agents))
            return False, f"[error] task needs a known agent ({known}) and a prompt"
        parent = session.executor
        child = new_session(_child_agent(session.agent, spec), session.root,
                            mode=parent.mode, approver=parent.approver, runner=parent.runner,
                            max_steps=session.max_steps)
        child.executor.rules = parent.rules
        tools = set(spec.tools) if spec.tools is not None else set(ALL_TOOLS)
        child.executor.allowed_tools = frozenset(tools - {"task"})   # no grandchildren
        child.executor.skills = parent.skills
        child.checkpoints = session.checkpoints       # a child's edits undo with the turn
        child.executor.before_write = session.checkpoints.snapshot
        result = child.turn(prompt)
        counter["n"] += 1
        record = {"agent": spec.name, "index": counter["n"], "steps": result.steps,
                  "ledger_head": result.checkpoint, "chain_ok": result.verified}
        session.ledger.append("subagent", json.dumps(record, sort_keys=True), record)
        session.save_child_ledger(counter["n"], spec.name, child.ledger)
        return True, f"[{spec.name} | {result.steps} step(s) | ledger {result.checkpoint[:12]}]\n" \
            + result.final
    return run
