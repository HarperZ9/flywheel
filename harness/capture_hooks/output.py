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
PENDING_SETTINGS = ("Flywheel capture settings changed on disk and are not in effect. "
                    "Confirm with: flywheel traces capture confirm.")
PENDING_RETENTION = ("Flywheel retention has a policy change or a deletion plan waiting "
                     "for you. See: flywheel traces retention show.")


def failure_line(code: str, spooled: bool, *, event: str = "prompt") -> str:
    tail = "" if spooled else "; the failure record could not be written either"
    what = "session not archived" if event == "session-end" else "turn not recorded"
    return f"flywheel capture: {what} ({code}{tail}). {DOCTOR}"


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


def freeze_context(manifest: dict) -> str | None:
    """What the Claude Code prompt hook hands the model: the URLs frozen with
    their digests, and counts of refused and failed ones, never their text."""
    sources = [s for s in manifest.get("sources", []) if isinstance(s, dict)]
    if not sources and not manifest.get("refused") and not manifest.get("failed"):
        return None
    lines = ["[flywheel] sources named in this message, frozen before work:"]
    lines += [f"  frozen {s.get('url')} sha256:{s.get('sha256')}" for s in sources]
    if manifest.get("refused"):
        lines.append(f"  {manifest['refused']} refused (credential-bearing URL, not fetched)")
    if manifest.get("failed"):
        lines.append(f"  {manifest['failed']} could not be fetched")
    return "\n".join(lines)
