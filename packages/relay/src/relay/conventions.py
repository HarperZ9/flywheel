"""conventions.py — fold a project's own conventions into the agent's system prompt.

A named, real gap versus aider (which auto-loads a CONVENTIONS.md): relay had no
way for a repo to state its own house rules once and have every agent run honor
them. This is the zero-dep version: look for a small set of well-known filenames
at the agent's root and fold the first match in, verbatim (never summarized, so
nothing it said is silently trimmed) and length-bounded (so a huge file cannot
blow a small local model's context).
"""
from __future__ import annotations

import os

# Checked in order; first match wins. Covers this ecosystem's own convention
# (AGENTS.md) and the two most common community names.
FILENAMES = ("AGENTS.md", "CONVENTIONS.md", ".relay/CONVENTIONS.md")
MAX_CHARS = 8000


def load_conventions(root: str, *, filenames=FILENAMES, max_chars: int = MAX_CHARS):
    """The first matching conventions file under root, or None if none exists.
    Returns {"path", "text", "truncated"} — text is capped at max_chars so an
    oversized file degrades (truncated, flagged) rather than blowing the context."""
    for name in filenames:
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        return {"path": name, "text": text[:max_chars], "truncated": len(text) > max_chars}
    return None


def with_conventions(system: str, root: str, **kw) -> str:
    """`system` with the project's conventions appended, or unchanged if none exist."""
    found = load_conventions(root, **kw)
    if not found:
        return system
    tail = "\n[... truncated ...]" if found["truncated"] else ""
    return f"{system}\n\nProject conventions ({found['path']}):\n{found['text']}{tail}"
