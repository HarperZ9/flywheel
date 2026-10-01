"""install.py -- the settings block that mounts the hook on an external harness.

Claude Code: a PreToolUse and PostToolUse command hook with matcher "*" (which
covers mcp__<server>__<tool> as well as builtins) and a UserPromptSubmit hook
that records the owner's goal. The hook timeout is set well above the hook's
own internal deadline so the vendor timeout never fires first. Codex: the same
hook_cli with the codex adapter, written to ~/.codex/hooks.json or a repo .codex/.
"""
from __future__ import annotations

import subprocess

HOOK_TIMEOUT = 30


def _q(part: str) -> str:
    """Quote a path with spaces. An unquoted interpreter path such as
    C:/Program Files/Python makes the shell fail with a non-2 exit, which
    the vendor treats as non-blocking: the hook would silently allow."""
    if part and not any(c in part for c in ' \t"'):
        return part
    return '"' + part.replace('"', '\\"') + '"'


def _command(python: str, client: str, home: str, *flags: str) -> str:
    parts = [python, "-P", "-E", "-m", "harness.preaction.hook_cli", client, "--home", home, *flags]
    return " ".join(_q(p) for p in parts)


def importable(python: str) -> tuple:
    """True when the interpreter the hook names can import the hook with the
    same flags. A hook that cannot import exits 1, and exit 1 does not block."""
    try:
        proc = subprocess.run([python, "-P", "-E", "-c", "import harness.preaction.hook_cli"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return proc.returncode == 0, (proc.stderr or "").strip()[-300:]


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
