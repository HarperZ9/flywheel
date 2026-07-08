"""local_loop.py — the agentic loop: local model + gated tools + witnessed ledger.

This is what turns the chat client into an actual local coding agent. The model
proposes tool calls in the text protocol, the executor runs them under the gate,
observations are fed back, and the whole trajectory (turns + tool calls +
results) is appended to a hash-chained SessionLedger. The loop terminates when
the model stops emitting TOOL lines (final answer) or max_steps is hit — always
returning a re-verifiable checkpoint.
"""
from __future__ import annotations

import json

from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, parse_tool_calls


def run_agent(agent, goal: str, executor: ToolExecutor,
              ledger: "SessionLedger | None" = None, *, max_steps: int = 6) -> dict:
    """Run the goal to completion (or max_steps). Returns the final answer, the
    step count, and the ledger checkpoint + verify verdict."""
    ledger = ledger if ledger is not None else SessionLedger()
    if TOOLS_SYSTEM not in agent.system:
        agent.system = agent.system + "\n\n" + TOOLS_SYSTEM

    ledger.append("user", goal)
    message = goal
    for step in range(1, max_steps + 1):
        resp = agent.send(message)
        text = resp["content"][0]["text"] if resp.get("content") else ""
        ledger.append("assistant", text, {
            "backend": resp.get("backend"),
            "receipt": resp.get("x_receipt", {}).get("receipt_id")})

        calls = parse_tool_calls(text)
        if not calls:
            return _done(text, step, ledger)

        observations = []
        for name, args in calls:
            res = executor.execute(name, args)
            ledger.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")
            ledger.append("tool_result", res.output, {"tool": name, "ok": res.ok})
            observations.append(f"TOOL {name} -> {'ok' if res.ok else 'FAIL'}:\n{res.output}")

        message = ("TOOL RESULTS:\n" + "\n\n".join(observations) +
                   "\n\nContinue if you need more tools, otherwise give the final "
                   "answer with no TOOL line.")

    return _done("[max_steps reached without a final answer]", max_steps, ledger)


def _done(final: str, steps: int, ledger: SessionLedger) -> dict:
    return {"final": final, "steps": steps,
            "checkpoint": ledger.checkpoint(), "verified": ledger.verify(),
            "entries": len(ledger.entries), "ledger": ledger}
