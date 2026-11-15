"""textblock_scope.py -- the optional glob scope of a personality block.

W1 lets a personality block say which files it applies to (`data.applies_to`,
a list of glob patterns). No catalog surface can load a block for some files
and not others, so the scope is carried two ways in the region grammar
(`canon.textblock/v1`):

  <!-- canon:block id="react" applies="src/**/*.tsx|src/**/*.ts" -->
  ## React rules
  Applies to: src/**/*.tsx, src/**/*.ts
  ...body...

The `applies` attribute on the sentinel is the authoritative, machine-read copy,
and it round-trips exactly. The visible `Applies to:` line is generated from it
so the model reading the file sees the scope as advice. On ingest the line must
match the attribute exactly and is removed, so an edited line is a refusal, not
a silent change. A block without the attribute is parsed as before, and a body
that happens to start with `Applies to:` is ordinary text there.
"""
from __future__ import annotations

APPLIES_PREFIX = "Applies to: "
_FORBIDDEN = ('"', "<", ">", "|", "\n", "\r")


def check_applies(value: object) -> str | None:
    """None when `value` is a usable scope, else the reason it is not."""
    if not isinstance(value, list) or not value:
        return "applies_to must be a non-empty list of glob patterns"
    for pattern in value:
        if not isinstance(pattern, str) or not pattern.strip():
            return "applies_to holds an empty or non-text pattern"
        if any(ch in pattern for ch in _FORBIDDEN):
            return f"applies_to pattern carries a reserved character: {pattern!r}"
    return None


def attribute(globs: list[str]) -> str:
    return f' applies="{"|".join(globs)}"'


def visible_line(globs: list[str]) -> str:
    return APPLIES_PREFIX + ", ".join(globs)


def strip_visible(block_id: str, body_lines: list[str], globs: list[str]) -> list[str]:
    """The body lines after the generated scope line. Raises ValueError when
    the line is missing or does not match the sentinel's attribute."""
    expected = visible_line(globs)
    if not body_lines or body_lines[0] != expected:
        raise ValueError(f"block {block_id!r}: the Applies to line does not match "
                         "its sentinel")
    return body_lines[1:]
