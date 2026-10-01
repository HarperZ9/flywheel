"""install.py -- the settings block that mounts the hook on an external harness.

Claude Code: a PreToolUse and PostToolUse command hook with matcher "*" (which
covers mcp__<server>__<tool> as well as builtins) and a UserPromptSubmit hook
that records the owner's goal. The hook timeout is set well above the hook's
own internal deadline so the vendor timeout never fires first. Codex: the same
hook_cli with the codex adapter, written to ~/.codex/hooks.json or a repo .codex/.
"""
from __future__ import annotations

HOOK_TIMEOUT = 30


def _command(python: str, client: str, home: str, *flags: str) -> str:
    parts = [python, "-P", "-E", "-m", "harness.preaction.hook_cli", client, "--home", home, *flags]
    return " ".join(parts)


def settings_block(client: str, *, python: str, home: str) -> dict:
    if client not in ("claude-code", "codex"):
        raise ValueError("client must be claude-code or codex")
    hold_flags = () if client == "claude-code" else ("--hold-mode", "deny")

    def entry(*flags):
        return {"matcher": "*", "hooks": [{"type": "command",
                "command": _command(python, client, home, *flags), "timeout": HOOK_TIMEOUT}]}

    return {"hooks": {
        "PreToolUse": [entry(*hold_flags)],
        "PostToolUse": [entry("--post")],
        "UserPromptSubmit": [entry("--event", "prompt")],
    }}
