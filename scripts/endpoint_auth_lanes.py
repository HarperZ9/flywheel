"""The account lanes the harness reports presence for, and nothing more.

One entry per way a provider can be activated on this machine. A lane names
the local prerequisite the status command looks for, never a credential: an
executable on PATH for a subscription CLI, an environment variable's presence
for an API key. Nothing here reads a token store or a key's value.

The list lives apart from run_endpoint_auth_status.py so a new peer harness is
one entry rather than an edit to the command that renders them.
"""

from __future__ import annotations

import os

_WINDOWS = os.name == "nt"


def _commands(*names: str) -> list[str]:
    """PATH candidates for a CLI, .exe first on Windows."""
    return [f"{name}.exe" for name in names] + list(names) if _WINDOWS else list(names)


LANES = [
    {
        "id": "claude_subscription",
        "provider": "claude",
        "mode": "plan",
        "kind": "subscription_cli",
        "cli_env": "CLAUDE_CLI",
        "fallback_commands": ["claude.exe", "claude"] if _WINDOWS else ["claude"],
        "next_action": (
            "Authenticate the official Claude CLI in an operator-controlled "
            "terminal. Set CLAUDE_CLI only if the command is nonstandard."
        ),
    },
    {
        "id": "claude_api",
        "provider": "claude",
        "mode": "api",
        "kind": "api_key",
        "key_env": "ANTHROPIC_API_KEY",
        "next_action": "Set ANTHROPIC_API_KEY in the local secret environment.",
    },
    {
        "id": "codex_subscription",
        "provider": "codex",
        "mode": "plan",
        "kind": "subscription_cli",
        "cli_env": "CODEX_CLI",
        "fallback_commands": ["codex.cmd", "codex"] if _WINDOWS else ["codex"],
        "next_action": (
            "Authenticate the official Codex CLI in an operator-controlled "
            "terminal. Set CODEX_CLI only if the command is nonstandard."
        ),
    },
    {
        "id": "codex_api",
        "provider": "codex",
        "mode": "api",
        "kind": "api_key",
        "key_env": "OPENAI_API_KEY",
        "next_action": "Set OPENAI_API_KEY in the local secret environment.",
    },
    {
        # cursor-agent authenticates through the Cursor account, so presence of
        # the CLI is the only local prerequisite this command can see. There is
        # no documented API-key lane for it, so none is declared.
        "id": "cursor_subscription",
        "provider": "cursor",
        "mode": "plan",
        "kind": "subscription_cli",
        "cli_env": "CURSOR_CLI",
        "fallback_commands": _commands("cursor-agent"),
        "next_action": (
            "Install and authenticate the official Cursor CLI (cursor-agent) "
            "in an operator-controlled terminal. Set CURSOR_CLI only if the "
            "command is nonstandard."
        ),
    },
]
