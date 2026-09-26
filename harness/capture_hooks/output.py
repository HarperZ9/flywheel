"""What a hook prints, per client and event (7.1).

Claude Code Stop and SessionEnd: a failure exits 1 with one stderr line and
empty stdout; Claude Code shows "<hook name> hook error" with that line. The
Claude Code prompt hook and every Codex hook exit 0 and carry a message in
`systemMessage`. No hook ever exits 2, so capture never blocks the owner's
work, and no message carries content, a path other than the notice's working
directory, or a secret.
"""
from __future__ import annotations

import json

DOCTOR = "Run: flywheel traces doctor"


def failure_line(code: str, spooled: bool) -> str:
    tail = "" if spooled else "; the failure record could not be written either"
    return f"flywheel capture: turn not recorded ({code}{tail}). {DOCTOR}"


def unacked_line(count: int, since: str | None) -> str:
    when = f" since {since[11:16]} UTC" if since and len(since) >= 16 else ""
    noun = "capture" if count == 1 else "captures"
    return f"Flywheel: {count} {noun} failed{when}. Run flywheel traces doctor."


def suppression_line(cwd: str) -> str:
    return (f"Flywheel capture is off here (FLYWHEEL_CAPTURE=off in {cwd}). "
            "This session is not recorded.")


def _loud_exit(client: str, event: str) -> bool:
    return client == "claude-code" and event in ("stop", "session-end")


def render(client: str, event: str, *, failure: str | None = None,
           messages: list[str] | None = None, context: str | None = None
           ) -> tuple[int, str, str]:
    """(exit code, stdout, stderr) for one hook run."""
    messages = [m for m in (messages or []) if m]
    if failure and _loud_exit(client, event):
        return 1, "", failure + "\n"
    if failure:
        messages.insert(0, failure)
    doc = {}
    if messages:
        doc["systemMessage"] = " ".join(messages)
    if context and client == "claude-code" and event == "prompt":
        doc["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit",
                                     "additionalContext": context}
    return 0, (json.dumps(doc) if doc else ""), ""
