"""frontmatter.py -- R2: a constrained single-quoted-scalar frontmatter codec.

This is not a general YAML writer or loader. It emits exactly two value shapes
and reads exactly one key back:

- Flat single-quoted scalar ``key: '<v>'`` with every ``'`` doubled to ``''``
  (the sole escape a single-quoted YAML scalar defines). Values are guaranteed
  single-line by the caller (``render_note`` refuses a line break in an
  authoritative content field) and re-checked here.
- The authoritative key ``canon: '<J>'`` where ``<J>`` is ``record.to_json()``
  reused verbatim: ``json.dumps(sort_keys=True)`` is single-line even with
  embedded quotes, newlines, and unicode, so the whole envelope rides one
  physical line.

The reader runs no YAML loader (the ``!!python/object`` RCE trap is inert): it
normalizes CRLF to LF, anchors to the leading ``---`` fence, takes the block up
to the next line that is exactly ``---``, finds the one line beginning
``canon: '``, undoes the escape, and reconstructs with ``json.loads`` +
``Record.from_dict``. Every other scalar and the body are ignored on read; they
are a one-way projection (D-27).
"""
from __future__ import annotations

import json

from canon.schema import Record, schema_tag_for

FENCE = "---"
_CANON_PREFIX = "canon: '"

# The fixed frontmatter key order, always emitted in this sequence (D-28).
FRONTMATTER_KEYS = (
    "canon_schema", "kind", "id", "scope", "title", "aliases", "canon",
)


class FrontmatterError(ValueError):
    """A note's frontmatter is missing, malformed, or ambiguous."""


def _sq_escape(value: str) -> str:
    return value.replace("'", "''")


def _sq_unescape(value: str) -> str:
    return value.replace("''", "'")


def emit_scalar(value: str) -> str:
    """A single-quoted YAML scalar with ``'`` doubled. Single-line by contract."""
    return f"'{_sq_escape(value)}'"


def emit_alias_list(ids: list[str]) -> str:
    """A one-line flow sequence ``['a', 'b']`` with each element ``''``-escaped."""
    return "[" + ", ".join(emit_scalar(i) for i in ids) + "]"


def _require_single_line(label: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise FrontmatterError(f"{label} scalar must be a single physical line")


def emit_frontmatter(
    record: Record, *, title: str, aliases: list[str] | None = None
) -> str:
    """Emit the fenced frontmatter block for ``record``.

    ``title`` is the display label the caller also uses for the note heading; it
    is a projection, never read back. ``aliases`` defaults to the record id
    alone; the note codec passes a longer list when an id needs a wikilink-safe
    fallback token (D-25). The ``canon:`` line is the authoritative carrier and
    is asserted single-line.

    ``FRONTMATTER_KEYS`` drives the emission order (D-28): each key's value is
    produced here and the block is written in the constant's sequence, so the two
    cannot drift.
    """
    payload = record.to_json()
    _require_single_line("canon", payload)
    _require_single_line("id", record.id)
    _require_single_line("title", title)
    values = {
        "canon_schema": emit_scalar(schema_tag_for(record.kind)),
        "kind": emit_scalar(record.kind),
        "id": emit_scalar(record.id),
        "scope": emit_scalar(record.scope),
        "title": emit_scalar(title),
        "aliases": emit_alias_list([record.id] if aliases is None else aliases),
        "canon": emit_scalar(payload),
    }
    lines = [FENCE, *(f"{key}: {values[key]}" for key in FRONTMATTER_KEYS), FENCE]
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> dict:
    """Return the record dict carried by the ``canon:`` key.

    Anchors to the leading fence and reads only the ``canon:`` line; every other
    scalar and the body are ignored. Raises ``FrontmatterError`` on a missing
    fence, a missing or duplicated ``canon:`` key, or a malformed scalar.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0] != FENCE:
        raise FrontmatterError("note does not open with a frontmatter fence")
    close = None
    for i in range(1, len(lines)):
        if lines[i] == FENCE:
            close = i
            break
    if close is None:
        raise FrontmatterError("frontmatter fence is not closed")
    canon_lines = [ln for ln in lines[1:close] if ln.startswith(_CANON_PREFIX)]
    if len(canon_lines) != 1:
        raise FrontmatterError(
            f"expected exactly one canon key, found {len(canon_lines)}"
        )
    raw = canon_lines[0][len("canon: "):]
    if len(raw) < 2 or not (raw.startswith("'") and raw.endswith("'")):
        raise FrontmatterError("malformed canon scalar")
    return json.loads(_sq_unescape(raw[1:-1]))


def record_from_note(text: str) -> Record:
    """Reconstruct a ``Record`` from a note's ``canon:`` payload."""
    return Record.from_dict(parse_frontmatter(text))
