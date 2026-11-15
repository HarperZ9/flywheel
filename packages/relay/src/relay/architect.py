"""Planning helper for Relay architect mode.

Architect mode runs one backend for a planning turn and passes the attributed
plan to the implementing agent as context. The plan is a proposal; the
implementer still reads the real code and may choose a better path.
"""
from __future__ import annotations

_PLAN_PROMPT = (
    "You are planning a code change, not writing it. Read the task below and "
    "describe a concise, concrete step-by-step plan: which files to touch, what "
    "functions to add or change, and the approach. Do not write code and do not "
    "emit any TOOL line; a separate step will implement your plan.\n\nTask: {goal}"
)


def plan(planner, goal: str) -> dict:
    """Ask a planner agent for an attributed implementation proposal."""
    resp = planner.send(_PLAN_PROMPT.format(goal=goal))
    text = resp["content"][0]["text"] if resp.get("content") else ""
    return {"text": text, "backend": resp.get("backend", "?")}


def with_plan(goal: str, planned: dict) -> str:
    """Append the planner's proposal to the original goal without replacing it."""
    return (
        f"{goal}\n\n"
        f"A planning pass ({planned['backend']}) proposed this approach:\n"
        f"{planned['text']}\n\n"
        "Implement it. Adapt if you find a better path once you inspect the "
        "actual code."
    )
