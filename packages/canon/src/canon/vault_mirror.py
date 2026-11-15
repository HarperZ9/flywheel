"""vault_mirror.py -- R2: the whole-vault mirror orchestrator.

Module 2 projects one record to one note. This is the write-many layer over that
codec: it renders the whole pool into a vault (one note per record) plus a
MEMORY.md hub that indexes them, and it owns the three guarantees a single-note
codec cannot.

Containment. Every write resolves to `{scope}/{derived}.md` or `MEMORY.md` under
one injected vault root. The root is passed at call time and never stored, so
this source carries no operator path. A traversal, an absolute escape, the root
itself, or an ad-hoc path is refused before a byte moves (`is_vault_write_allowed`,
mirroring registry.py's lexical allow-list, D-31).

Ownership. A file already at a target path that does not parse as a canon note is
off-limits and the whole plan fails closed (D-30) -- the mirror never clobbers a
hand-authored file. A canon note whose on-disk name does not re-derive from its
own content is a spoof and is refused, so a hostile filename cannot smuggle a
record under a name the pool did not choose. A note whose visible body was
hand-edited but whose `canon:` carrier is intact is overwritten wholesale (the
carrier, not the body, is authoritative -- D-27).

All-or-nothing. The whole set (notes + hub) is planned -- rendered, keyed,
contained, classified against what is on disk -- before a single write commits.
One record that render refuses aborts the plan with zero files written. A record
dropped from the pool leaves its stale note reported as an orphan and never
deleted (D-32); deletion is a human's call, not the mirror's.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from canon.backends.base import record_key
# The hub orders exactly like the surface renderer: clock-free create_ord
# ascending, id tie-break, absent ordinal last. Reusing layering's key locks the
# two orders together rather than letting them drift.
from canon.layering import _sort_key
from canon.schema import (
    KIND_ADR_DECISION,
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_RESEARCH_ARTIFACT_REF,
    KIND_SYNTHESIZED_PERSONA_L3,
    SCOPES,
    Record,
)
from canon.vault import (
    VaultError,
    _display_title,
    derive_note_name,
    ingest_note,
    render_note,
)

_HUB_RELPATH = "MEMORY.md"
_HUB_H1 = "# canon memory index"
_HUB_MARKER = "<!-- canon:vault-hub v1 -- generated; edits here are not durable -->"
# Every rendered hub opens with this two-line head, so it doubles as the
# ownership token: a MEMORY.md that starts with it is canon's own to overwrite;
# one that does not is a hand-authored file the mirror must not clobber.
_HUB_HEAD = f"{_HUB_H1}\n{_HUB_MARKER}"
_HUB_CAP = 80


@dataclass(frozen=True, slots=True)
class VaultResult:
    """The outcome for one vault path: a note or the hub written or unchanged, or
    a stale canon note reported as an orphan (never written, never deleted).
    `record_key` is the record the path carries, or None for the hub."""

    path: str
    status: str
    record_key: str | None
    content: str | None


def is_vault_write_allowed(path: str, *, vault: str) -> bool:
    """True only if `path` resolves to a legal vault target under `vault`.

    A legal target is `{scope}/<name>.md` for a known scope, or the top-level
    `MEMORY.md` hub, and nothing else. Containment is lexical and case-folded
    (`normcase`): refuse the root itself, require `commonpath` to be the root (so
    a traversal that escapes fails), then check the relative tail's shape. It is
    the one lexical gate for both writes and read-side note-target recognition.
    """
    root = os.path.normcase(os.path.normpath(vault))
    target = os.path.normcase(os.path.normpath(path))
    if target == root:
        return False
    try:
        if os.path.commonpath([root, target]) != root:
            return False
    except ValueError:  # different drives, or a mix of absolute and relative
        return False
    parts = os.path.relpath(target, root).split(os.sep)
    if len(parts) == 1:
        return parts[0] == os.path.normcase(_HUB_RELPATH)
    if len(parts) == 2:
        scopes = {os.path.normcase(s) for s in SCOPES}
        return parts[0] in scopes and parts[1].endswith(".md")
    return False


def assert_under_vault_root(path: str, *, vault: str) -> None:
    """Raise VaultError unless `path` is a legal vault target under `vault`."""
    if not is_vault_write_allowed(path, vault=vault):
        raise VaultError(f"path is not an allowed vault target: {path!r}")


def _flatten_ws(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ")


def _truncate(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap] + "..."


def _escape_hub_title(title: str) -> str:
    """One hub-safe line: cap, then escape `\\`/`[`/`]`. Truncate before escaping
    (the cap counts visible chars, never leaving a dangling `\\`); escape `\\`
    first so `\\](url)` cannot fold to a live link-closing `]` (D-33, hub leg)."""
    flat = _truncate(_flatten_ws(title), _HUB_CAP)
    return flat.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _hook(record: Record) -> str:
    """A one-line preview for the hub entry, drawn from the record's own body."""
    data = record.data if isinstance(record.data, dict) else {}
    kind = record.kind
    if kind == KIND_PERSONALITY_BLOCK:
        raw = data.get("body", "")
    elif kind == KIND_ADR_DECISION:
        raw = data.get("decision", "")
    elif kind in (KIND_EPISODIC_MEMORY, KIND_SYNTHESIZED_PERSONA_L3):
        raw = data.get("text", "")
    elif kind == KIND_RESEARCH_ARTIFACT_REF:
        raw = data.get("locator", "")
    else:  # pragma: no cover -- render refuses unknown kinds upstream
        raw = ""
    return _truncate(_flatten_ws(str(raw)), _HUB_CAP)


def _hub_line(record: Record) -> str:
    title = _escape_hub_title(_display_title(record))
    return f"- [{title}]({derive_note_name(record)}) -- {_hook(record)}"


def render_hub(records: list[Record]) -> str:
    """Render the MEMORY.md hub: an H1, the generated-marker, then one H2 per
    non-empty scope (global before workspace) with one entry per note in the
    surface renderer's order. An empty pool is the head alone; an empty scope
    omits its H2."""
    sections: list[str] = []
    for scope in SCOPES:
        recs = sorted((r for r in records if r.scope == scope), key=_sort_key)
        if not recs:
            continue
        sections.append("\n".join([f"## {scope}"] + [_hub_line(r) for r in recs]))
    if not sections:
        return _HUB_HEAD + "\n"
    return _HUB_HEAD + "\n\n" + "\n\n".join(sections) + "\n"


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _abs(vault: str, relpath: str) -> str:
    return os.path.normpath(os.path.join(vault, relpath))


def _render_targets(records: list[Record]) -> dict[str, tuple[Record, str]]:
    """Map each record to its note relpath, refusing a duplicate record_key and a
    filename collision, and rendering each note (which refuses a bad record). All
    three refusals happen here, before any path resolves or any byte is read."""
    targets: dict[str, tuple[Record, str]] = {}
    seen: set[str] = set()
    for record in records:
        key = record_key(record)
        if key in seen:
            raise VaultError(f"duplicate record_key in pool: {key!r}")
        seen.add(key)
        relpath = derive_note_name(record)
        if relpath in targets:
            raise VaultError(f"note filename collision: {relpath!r}")
        targets[relpath] = (record, render_note(record))
    return targets


def _require_canon_at(text: str, relpath: str) -> Record:
    """The existing file at `relpath` must be a canon note whose name re-derives
    from its own content, or the plan fails closed."""
    try:
        record = ingest_note(_normalize(text))
    except VaultError as exc:
        raise VaultError(
            f"existing file at vault target is not a canon note: {relpath!r}"
        ) from exc
    if derive_note_name(record) != relpath:
        raise VaultError(f"vault note name does not match its content: {relpath!r}")
    return record


def _discover_orphans(targets, *, vault, read_text, list_dir):
    """Canon notes on disk under the mirror whose record_key is absent from the
    pool. A stray non-canon file that is not a target is left alone; a canon note
    whose name does not re-derive from its content is a spoof and is refused.
    Comparisons fold case (`normcase`), and containment reuses the write
    allow-list, so a case-only variant of a target is not misread as a spoof and
    an entry that is not a legal note target is skipped before it is read."""
    orphans: list[tuple[str, Record]] = []
    hub_nc = os.path.normcase(_HUB_RELPATH)
    target_ncs = {os.path.normcase(k) for k in targets}
    for relpath in list_dir(vault):
        norm = relpath.replace("\\", "/")
        norm_nc = os.path.normcase(norm)
        if norm_nc == hub_nc or norm_nc in target_ncs:
            continue
        abs_path = _abs(vault, norm)
        if not is_vault_write_allowed(abs_path, vault=vault):
            continue
        content = read_text(abs_path)
        if content is None:
            continue
        try:
            record = ingest_note(_normalize(content))
        except VaultError:
            continue
        if os.path.normcase(derive_note_name(record)) != norm_nc:
            raise VaultError(f"vault note name does not match its content: {norm!r}")
        orphans.append((norm, record))
    return orphans


def _plan_notes(targets, *, vault, read_text):
    """Resolve, contain, and byte-compare every target note. A changed or new
    note is planned for write; a byte-identical one (after CRLF normalization) is
    reported unchanged and never rewritten."""
    planned: list[tuple[str, str]] = []
    results: list[VaultResult] = []
    for relpath in sorted(targets):
        record, note = targets[relpath]
        abs_path = _abs(vault, relpath)
        assert_under_vault_root(abs_path, vault=vault)
        existing = read_text(abs_path)
        key = record_key(record)
        if existing is not None:
            _require_canon_at(existing, relpath)
            if _normalize(existing) == note:
                results.append(VaultResult(abs_path, "unchanged", key, note))
                continue
        planned.append((abs_path, note))
        results.append(VaultResult(abs_path, "written", key, note))
    return planned, results


def _plan_hub(records, *, vault, read_text):
    """Plan the hub write, refusing to clobber a foreign MEMORY.md.

    An existing MEMORY.md that does not open with the generated head is a
    hand-authored file, not canon's own; the plan fails closed rather than
    overwrite it (the note targets' ownership rule, extended to the hub). A
    canon-owned hub is overwritten when it differs and skipped when it matches.
    """
    hub = render_hub(records)
    abs_path = _abs(vault, _HUB_RELPATH)
    assert_under_vault_root(abs_path, vault=vault)
    existing = read_text(abs_path)
    if existing is not None:
        if not _normalize(existing).startswith(_HUB_HEAD):
            raise VaultError(
                f"existing MEMORY.md is not a canon hub; refusing to clobber it: {abs_path!r}")
        if _normalize(existing) == hub:
            return None, VaultResult(abs_path, "unchanged", None, hub)
    return (abs_path, hub), VaultResult(abs_path, "written", None, hub)


def plan_vault(records, *, vault, read_text, write_text, list_dir):
    """Mirror the whole pool into the vault under `vault`, plan-then-commit.

    Every note and the hub are rendered, keyed, contained, and classified against
    what is on disk before the first write. Any refusal -- a duplicate key, a
    collision, a render refusal, an off-limits or spoofed existing file, a
    containment violation -- aborts with zero writes. Orphans are reported, never
    deleted. IO is injected: `read_text` returns None for an absent file,
    `list_dir` yields the POSIX relpaths present under the mirror.
    """
    targets = _render_targets(records)
    orphans = _discover_orphans(
        targets, vault=vault, read_text=read_text, list_dir=list_dir)
    planned, results = _plan_notes(targets, vault=vault, read_text=read_text)
    hub_write, hub_result = _plan_hub(records, vault=vault, read_text=read_text)
    results.append(hub_result)
    if hub_write is not None:
        planned.append(hub_write)
    for relpath, record in orphans:
        results.append(VaultResult(_abs(vault, relpath), "orphan", record_key(record), None))
    for abs_path, content in planned:
        write_text(abs_path, content)
    return results
