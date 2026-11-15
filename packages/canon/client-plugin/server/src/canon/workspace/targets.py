"""targets.py -- the agents a brief can be written for, and their size budgets.

A brief that overruns what its host reads is worse than a short one: Codex
truncates its instruction files past a fixed byte budget, and the tail it cuts
is whatever canon put last. Each target therefore carries two numbers for the
brief (bytes and lines) and, where the host documents one, a limit for the
whole instruction file.

The host numbers and where they come from, read 2026-09-23:

  codex        AGENTS.md files share one 32768-byte budget and are truncated
               past it (project_doc_max_bytes in the Codex source defaults and
               docs). High confidence. A hard limit: switch refuses to write
               past it.
  claude-code  the docs advise a CLAUDE.md under 200 lines. High confidence.
               Users report a warning above 40,000 characters (moderate).
  cursor       the rules docs say to keep a rule under 500 lines. High.
  copilot      the code review tutorial suggests at most about 1,000 lines per
               instruction file. High.
  gemini-cli   no documented limit. canon applies its own ceiling.

The brief budgets are canon's choices inside those limits, leaving room for the
personality blocks that share the file. They are defaults, and every command
that writes a brief accepts an override.
"""
from __future__ import annotations

from dataclasses import dataclass


class UnknownTarget(ValueError):
    """A target name that is not in the catalog."""


@dataclass(frozen=True, slots=True)
class Target:
    """One agent a brief can be written for. `harness` names the workspace
    surface in the write allow-list (None for a brief with no file)."""

    name: str
    display: str
    harness: str | None
    brief_bytes: int
    brief_lines: int
    file_bytes_limit: int | None
    file_lines_advice: int | None
    basis: str


TARGETS: tuple[Target, ...] = (
    Target("claude-code", "Claude Code", "claude-code", 12_000, 120, None, 200,
           "CLAUDE.md: docs advise under 200 lines (high); a 40,000-character "
           "warning is user-reported (moderate)"),
    Target("codex", "Codex CLI", "codex", 16_384, 400, 32_768, None,
           "AGENTS.md: project_doc_max_bytes 32768, truncated past it (high)"),
    Target("gemini-cli", "Gemini CLI", "gemini-cli", 16_384, 400, None, None,
           "GEMINI.md: no documented limit; canon's own ceiling"),
    Target("cursor", "Cursor", "cursor", 16_384, 250, None, 500,
           ".cursor/rules: docs advise a rule under 500 lines (high)"),
    Target("copilot", "GitHub Copilot", "copilot", 16_384, 400, None, 1_000,
           ".github/copilot-instructions.md: about 1,000 lines at most (high)"),
    Target("markdown", "Generic Markdown", None, 16_384, 400, None, None,
           "no host file; canon's own ceiling for a pasted brief"),
)

TARGET_NAMES = tuple(t.name for t in TARGETS)


def target_for(name: str) -> Target:
    for target in TARGETS:
        if target.name == name:
            return target
    raise UnknownTarget(f"unknown target {name!r}; expected one of {list(TARGET_NAMES)}")
