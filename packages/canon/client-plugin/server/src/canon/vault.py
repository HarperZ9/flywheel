"""vault.py -- R2: the one-record Obsidian-note codec.

A note is a whole-file markdown projection of exactly one canonical record. The
frontmatter `canon:` key carries `record.to_json()` verbatim and is the single
authoritative, lossless carrier of the whole envelope (see frontmatter.py). The
`#` heading, the per-kind rendered body, the `## canon links` trailer, and the
flat frontmatter scalars are a one-way projection: regenerated on every render
and never read back (D-27). `ingest_note` reconstructs from the JSON alone, so a
hand-edited body never changes the record.

Identity, not content, names the file: `derive_note_name` hashes the record's
`(scope, id)` key (`backends.base.record_key`) under a fixed domain string, so a
hostile id cannot forge a path (D-29). `render_note` refuses up front any record
it cannot faithfully project -- an invalid record (validator), a bare CR in
content (D-12 ported), or a research-artifact-ref carrying a temporal block --
rather than emit a note `ingest_note` would then reject. This is the R0
render-superset invariant (D-13) carried to the vault leg (D-33).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from canon.backends.base import record_key
from canon.frontmatter import FrontmatterError, emit_frontmatter, record_from_note
from canon.schema import (
    KIND_ADR_DECISION,
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_RESEARCH_ARTIFACT_REF,
    KIND_SYNTHESIZED_PERSONA_L3,
    SCOPES,
    Record,
)
from canon.validator import validate_record

# Domain-separation prefix for every vault-derived digest. A leading newline
# keeps the domain tag from running into the key it protects.
_DIGEST_DOMAIN = "canon-vault/v1\n"
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_SLUG_CAP = 60
# Characters that break Obsidian's `[[wikilink]]` grammar if they appear raw.
_WIKILINK_HOSTILE = frozenset("[]|#^\n\r")


class VaultError(Exception):
    """A note cannot be reconstructed into a valid record."""


class NoteRefused(VaultError):
    """A record cannot be projected to a note without loss or ambiguity, so
    render refuses it rather than emit a note the ingest leg would reject."""


def _slugify(text: str) -> str:
    """Fold `text` to a filesystem- and wikilink-safe `[a-z0-9-]` slug.

    NFKD-decompose, drop non-ASCII, casefold, collapse every other run to a
    single dash, strip leading/trailing dashes, cap at 60 chars. May return the
    empty string (an id that is all punctuation or non-ASCII); the caller
    supplies the `note` fallback.
    """
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    dashed = _NON_SLUG.sub("-", ascii_only.casefold()).strip("-")
    if len(dashed) > _SLUG_CAP:
        dashed = dashed[:_SLUG_CAP].strip("-")
    return dashed


def _digest(key: str) -> str:
    return hashlib.sha256((_DIGEST_DOMAIN + key).encode("utf-8")).hexdigest()[:16]


def derive_note_name(record: Record) -> str:
    """The note's relative path `{scope}/{slug}-{16hex}.md`.

    The digest is taken over `record_key` (`scope/id`) under a fixed domain, so
    it is stable, all-lowercase (case-fold portable), and never derived from
    body content. The raw id never becomes a path segment, so traversal and
    absolute-path escapes cannot form.

    Refuses a non-string or empty id (which `_slugify` would otherwise crash on)
    as a VaultError. The mirror derives the name before it renders, so this guard
    keeps a malformed id from crashing the derive leg before render can refuse it.
    """
    if not isinstance(record.id, str) or record.id == "":
        raise VaultError(f"record id must be a non-empty string: {record.id!r}")
    slug = _slugify(record.id) or "note"
    return f"{record.scope}/{slug}-{_digest(record_key(record))}.md"


def _has_cr(value: object) -> bool:
    """True iff a bare CR hides anywhere in a JSON-able content value."""
    if isinstance(value, str):
        return "\r" in value
    if isinstance(value, dict):
        return any(_has_cr(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_cr(v) for v in value)
    return False


def _display_title(record: Record) -> str:
    """The heading label, reused as the flat `title:` scalar (projection only)."""
    data = record.data if isinstance(record.data, dict) else {}
    kind = record.kind
    if kind in (KIND_PERSONALITY_BLOCK, KIND_ADR_DECISION):
        return str(data.get("title", record.id))
    if kind == KIND_EPISODIC_MEMORY:
        return f"Memory {record.id}"
    if kind == KIND_SYNTHESIZED_PERSONA_L3:
        return f"Persona {record.id}"
    if kind == KIND_RESEARCH_ARTIFACT_REF:
        return str(data.get("title") or data.get("locator", record.id))
    return record.id


def _link_token(target_id: str) -> str:
    """A wikilink-safe token for `[[...]]`.

    A clean id is used verbatim (Obsidian resolves it via the note's `aliases`).
    An id carrying a wikilink-hostile char cannot ride inside `[[...]]` without
    corrupting the link, so it falls back to a safe `{slug}-{digest}` token.
    """
    if any(ch in _WIKILINK_HOSTILE for ch in target_id):
        slug = _slugify(target_id) or "note"
        return f"{slug}-{_digest(target_id)}"
    return target_id


def _alias_list(record: Record) -> list[str]:
    """The note's `aliases`: the raw id, plus its wikilink-safe fallback token
    when the id is hostile. A link to this record from another note emits
    `_link_token(id)` (D-25); advertising that same token here is what makes the
    `[[token]]` link resolve. A clean id is its own token, so the list is just
    the id and no duplicate is added.
    """
    token = _link_token(record.id)
    return [record.id] if token == record.id else [record.id, token]


def emit_links(record: Record) -> str:
    """The `## canon links` trailer, or `""` when the record holds no relation.

    Links come only from the record's own relations -- `temporal.supersedes` and
    `data.source_ids` -- never from body prose. A body `[[wikilink]]` is opaque
    content, not a relation.
    """
    lines: list[str] = []
    temporal = record.temporal
    if temporal is not None and temporal.supersedes:
        lines.append(f"- Supersedes: [[{_link_token(temporal.supersedes)}]]")
    data = record.data if isinstance(record.data, dict) else {}
    source_ids = data.get("source_ids")
    if source_ids:
        rendered = ", ".join(f"[[{_link_token(str(s))}]]" for s in source_ids)
        lines.append(f"- Sources: {rendered}")
    if not lines:
        return ""
    return "\n## canon links\n" + "\n".join(lines) + "\n"


def _body_personality_block(record: Record, title: str) -> list[str]:
    return [f"# {title}", "", str(record.data.get("body", ""))]


def _body_adr(record: Record, title: str) -> list[str]:
    data = record.data
    parts = [
        f"# {title}",
        "",
        f"**Status:** {data.get('status', '')}",
        "",
        "## Context",
        "",
        str(data.get("context", "")),
        "",
        "## Decision",
        "",
        str(data.get("decision", "")),
    ]
    consequences = data.get("consequences")
    if consequences:
        parts += ["", "## Consequences", ""]
        parts += [f"- {c}" for c in consequences]
    return parts


def _body_memory_like(record: Record, heading: str) -> list[str]:
    data = record.data
    return [heading, "", str(data.get("text", "")), "", f"**Layer:** {data.get('layer', '')}"]


def _body_research_ref(record: Record, title: str) -> list[str]:
    data = record.data
    parts = [f"# {title}", "", f"**Locator:** {data.get('locator', '')}"]
    media_type = data.get("media_type")
    if media_type:
        parts += ["", f"**Media type:** {media_type}"]
    parts += ["", f"**Artifact hash:** {data.get('artifact_hash', '')}"]
    return parts


def _render_body(record: Record, title: str) -> str:
    kind = record.kind
    if kind == KIND_PERSONALITY_BLOCK:
        parts = _body_personality_block(record, title)
    elif kind == KIND_ADR_DECISION:
        parts = _body_adr(record, title)
    elif kind == KIND_EPISODIC_MEMORY:
        parts = _body_memory_like(record, f"# Memory {record.id}")
    elif kind == KIND_SYNTHESIZED_PERSONA_L3:
        parts = _body_memory_like(record, f"# Persona {record.id}")
    elif kind == KIND_RESEARCH_ARTIFACT_REF:
        parts = _body_research_ref(record, title)
    else:  # a workspace-state kind: heading only, the carrier holds the record
        parts = [f"# {title}"]
    return "\n".join(parts) + "\n"


def _refuse_if_non_list(label: str, value: object) -> None:
    """Refuse a present-but-non-list `value` an emitter iterates. A non-iterable
    raises a raw TypeError in the body/links loop, and a string or dict projects a
    garbage bullet list, so neither can be faithfully projected. Truthy-gated so a
    missing or empty field is a no-op, matching the emitters' own `if value:`."""
    if value and not isinstance(value, list):
        raise NoteRefused(
            f"{label} must be a list to project, got {type(value).__name__}")


def _refuse_unprojectable(record: Record, title: str) -> None:
    """Refuse residue the projection cannot faithfully carry, so render_note
    stays the fail-closed choke point (D-33).

    Four failure modes slip past the CR gate and the validator but break the
    projection, and each becomes NoteRefused here before a byte is emitted:

    - a bare LF in a single-line scalar (`id`, `title`), which `emit_frontmatter`
      would otherwise reject with a raw FrontmatterError;
    - a present, non-list `consequences` (only the adr body iterates it) or
      `source_ids` (the links trailer iterates it), via `_refuse_if_non_list`;
    - data the strict `canon:` JSON cannot encode -- a non-serializable value, or
      a NaN/Infinity that `json.dumps` would emit as a non-portable bareword that
      never equals itself on round-trip and silently fails the fidelity verdict.
    """
    for label, value in (("id", record.id), ("title", title)):
        if "\n" in value or "\r" in value:
            raise NoteRefused(f"{label} scalar is not a single physical line")
    data = record.data
    if record.kind == KIND_ADR_DECISION:
        _refuse_if_non_list("consequences", data.get("consequences"))
    _refuse_if_non_list("source_ids", data.get("source_ids"))
    try:
        json.dumps(record.to_dict(), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise NoteRefused(f"record data is not JSON-serializable: {exc}") from exc


def render_note(record: Record) -> str:
    """Project `record` to its whole-file note text (LF, single trailing NL).

    Refuses before emitting: an invalid record (every validator problem, which
    covers an unknown scope, an empty id, and a research-artifact-ref carrying a
    temporal block), a bare CR anywhere in the record's content, a bare LF in a
    single-line scalar, or data the carrier JSON cannot encode.
    """
    if _has_cr(record.id) or _has_cr(record.data) or (
        record.temporal is not None and _has_cr(record.temporal.supersedes)
    ):
        raise NoteRefused("bare CR in record content")
    problems = validate_record(record)
    if problems:
        raise NoteRefused("record is not valid: " + "; ".join(problems))
    title = _display_title(record)
    _refuse_unprojectable(record, title)
    frontmatter = emit_frontmatter(record, title=title, aliases=_alias_list(record))
    return frontmatter + _render_body(record, title) + emit_links(record)


def ingest_note(text: str) -> Record:
    """Reconstruct a valid record from a note's `canon:` JSON.

    The record comes from the JSON alone, never the visible body. Raises
    VaultError on a missing/malformed `canon:` key, a JSON the schema rejects, or
    a reconstructed record the validator rejects.
    """
    try:
        record = record_from_note(text)
    except (FrontmatterError, ValueError, KeyError) as exc:
        raise VaultError(f"note does not carry a reconstructable record: {exc}") from exc
    problems = validate_record(record)
    if problems:
        raise VaultError("ingested record is invalid: " + "; ".join(problems))
    return record
