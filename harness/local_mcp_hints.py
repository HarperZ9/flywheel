"""Title and hints for each tool the local-agent MCP server lists.

The server assembles its list from three places (its own tools, the context
memory tools, and the receipt tool), so the hints live here, applied once
where the list is built, rather than scattered across those modules.

What each hint rests on:

- health pings the local model tiers, and with `online` the provider tiers, so
  it reaches past the machine but changes nothing.
- chat spends a model call and, with `online`, sends the prompt to a provider.
- run drives an agent that can write and execute inside the granted workspace,
  so it is the one destructive tool.
- status and doctor answer from memory with no network.
- context health and preflight query the Canon context store through its own
  process; capture writes an event into that store.
- receipt inclusion reads the receipts ledger and changes nothing.
"""
from __future__ import annotations

from .mcp_annotations import annotated

# name: (title, read_only, destructive, idempotent, open_world)
HINTS: dict[str, tuple[str, bool, bool, bool, bool]] = {
    "local_agent_health": ("Check which model tiers answer", True, False, True, True),
    "local_agent_chat": ("Ask a model for one completion", False, False, False, True),
    "local_agent_run": ("Run an agent task in the workspace", False, True, False, True),
    "local-model.status": ("Local model lane status", True, False, True, False),
    "local-model.doctor": ("Local model lane readiness", True, False, True, False),
    "flywheel.context.health": ("Context store status", True, False, True, False),
    "flywheel.context.capture": ("Capture context into the store", False, False, False,
                                 False),
    "flywheel.context.preflight": ("Search the context store", True, False, True, False),
    "receipt.verify_inclusion": ("Check a receipt's log membership", True, False, True,
                                 False),
}


def hinted(tool: dict) -> dict:
    title, read_only, destructive, idempotent, open_world = HINTS[tool["name"]]
    return annotated(tool, title, read_only=read_only, destructive=destructive,
                     idempotent=idempotent, open_world=open_world)
