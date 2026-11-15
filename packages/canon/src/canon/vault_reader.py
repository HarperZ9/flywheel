"""vault_reader.py -- M4.2: whole-vault reader closing R2's write leg.

R2 writes a vault of one-note-per-record plus a MEMORY.md hub; M4.2 reads it
back. Every rule the write leg enforces has a symmetric read verdict, every
hostile input the write leg refuses has a typed read verdict, and the reader is
TOTAL: every refusal is a NoteVerdict, never a raise. Containment is one gate,
`vault_mirror.is_vault_write_allowed`, reused verbatim. Injected IO keeps the
module stdlib-only and testable against an in-memory FS. The pipeline runs in
strict order (containment -> hub -> read -> encoding -> normalize -> parse
-> reconstruct -> validate -> spoof -> scope match -> LOADED); each step maps
to one small handler so classify_vault_entry stays pure and IO-free.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from canon.backends.base import record_key
from canon.frontmatter import FrontmatterError, parse_frontmatter
from canon.schema import Record, SCOPES
from canon.textutil import _normalize_newlines
from canon.validator import validate_record
from canon.vault import VaultError, derive_note_name
from canon.vault_mirror import is_vault_write_allowed

_HUB_RELPATH = "MEMORY.md"

LOADED = "LOADED"
REFUSED_MISSING_FENCE = "REFUSED_MISSING_FENCE"
REFUSED_UNCLOSED_FENCE = "REFUSED_UNCLOSED_FENCE"
REFUSED_NO_CANON_KEY = "REFUSED_NO_CANON_KEY"
REFUSED_MULTIPLE_CANON_KEYS = "REFUSED_MULTIPLE_CANON_KEYS"
REFUSED_MALFORMED_SCALAR = "REFUSED_MALFORMED_SCALAR"
REFUSED_INVALID_JSON = "REFUSED_INVALID_JSON"
REFUSED_INVALID_SCHEMA = "REFUSED_INVALID_SCHEMA"
REFUSED_INVALID_RECORD = "REFUSED_INVALID_RECORD"
REFUSED_SPOOF = "REFUSED_SPOOF"
REFUSED_MIS_SCOPE = "REFUSED_MIS_SCOPE"
REFUSED_DUPLICATE_KEY = "REFUSED_DUPLICATE_KEY"
REFUSED_NAME_COLLISION = "REFUSED_NAME_COLLISION"
SKIPPED_HUB = "SKIPPED_HUB"
SKIPPED_NOT_ALLOWED = "SKIPPED_NOT_ALLOWED"
SKIPPED_ABSENT = "SKIPPED_ABSENT"
SKIPPED_NOT_MARKDOWN = "SKIPPED_NOT_MARKDOWN"
SKIPPED_ENCODING = "SKIPPED_ENCODING"

OK_STATUSES = frozenset({
    LOADED, SKIPPED_HUB, SKIPPED_NOT_ALLOWED, SKIPPED_ABSENT,
    SKIPPED_NOT_MARKDOWN, SKIPPED_ENCODING,
})

# BOM leading chars a Latin-1-decoded UTF-16/UTF-32 header lands as. UTF-8 BOM
# (U+FEFF) is NOT here: it falls through to REFUSED_MISSING_FENCE.
_ENC_BOM_PREFIXES = ("ÿþ\x00\x00", "\x00\x00þÿ", "ÿþ", "þÿ")


@dataclass(frozen=True, slots=True)
class NoteVerdict:
    """One relpath -> one verdict. `record` is present iff status == LOADED."""

    status: str
    relpath: str
    record: Record | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ReadPlan:
    """Phase 1 output. Verdicts in listing order (sorted by caller)."""

    root: str
    verdicts: tuple[NoteVerdict, ...]


@dataclass(frozen=True, slots=True)
class VaultReadResult:
    """Phase 2 output. `ok` is True iff every verdict is in OK_STATUSES."""

    pool: tuple[Record, ...]
    refusals: tuple[NoteVerdict, ...]
    skipped: tuple[NoteVerdict, ...]
    counts: dict[str, int] = field(default_factory=dict)
    ok: bool = True


def _abs(root: str, relpath: str) -> str:
    return os.path.normpath(os.path.join(root, relpath))


def _rel_parts(root: str, target: str) -> list[str] | None:
    try:
        return os.path.relpath(target, root).split(os.sep)
    except ValueError:  # cross-drive on Windows, or abs/rel mix
        return None


def _pre_containment_verdict(root: str, relpath: str) -> NoteVerdict | None:
    """Return a NoteVerdict for entries the reader should not open, else None.

    Distinguishes SKIPPED_HUB (top-level MEMORY.md), SKIPPED_NOT_MARKDOWN (a
    scope-directory entry lacking `.md`), and SKIPPED_NOT_ALLOWED (everything
    else the write-leg gate refuses). One gate, three verdicts.
    """
    norm_rel = relpath.replace("\\", "/")
    if os.path.normcase(norm_rel) == os.path.normcase(_HUB_RELPATH):
        return NoteVerdict(SKIPPED_HUB, relpath)
    target = _abs(root, norm_rel)
    if is_vault_write_allowed(target, vault=root):
        return None
    parts = _rel_parts(os.path.normpath(root), target)
    if parts is None:
        return NoteVerdict(SKIPPED_NOT_ALLOWED, relpath, reason="cross-drive")
    scope_ncs = {os.path.normcase(s) for s in SCOPES}
    if (len(parts) == 2 and os.path.normcase(parts[0]) in scope_ncs
            and not parts[1].endswith(".md")):
        return NoteVerdict(SKIPPED_NOT_MARKDOWN, relpath)
    return NoteVerdict(SKIPPED_NOT_ALLOWED, relpath)


def _encoding_verdict(value: object, relpath: str) -> NoteVerdict | None:
    """A bytes return or a Latin-1-decoded UTF-16/UTF-32 header is
    SKIPPED_ENCODING. A str starting with the UTF-8 BOM (\\ufeff) falls through
    to REFUSED_MISSING_FENCE (never silently stripped)."""
    if isinstance(value, bytes):
        return NoteVerdict(SKIPPED_ENCODING, relpath, reason="bytes returned")
    if isinstance(value, str) and any(value.startswith(b) for b in _ENC_BOM_PREFIXES):
        return NoteVerdict(SKIPPED_ENCODING, relpath, reason="UTF-16/UTF-32 BOM")
    return None


def _frontmatter_error_status(msg: str) -> str:
    if "does not open with a frontmatter fence" in msg:
        return REFUSED_MISSING_FENCE
    if "fence is not closed" in msg:
        return REFUSED_UNCLOSED_FENCE
    if "expected exactly one canon key" in msg:
        return REFUSED_NO_CANON_KEY if "found 0" in msg else REFUSED_MULTIPLE_CANON_KEYS
    if "malformed canon scalar" in msg:
        return REFUSED_MALFORMED_SCALAR
    return REFUSED_MALFORMED_SCALAR


def _parse_and_reconstruct(text: str, relpath: str) -> NoteVerdict:
    """Steps 7 + 8 + 9: frontmatter parse -> Record.from_dict -> validator."""
    try:
        payload = parse_frontmatter(text)
    except FrontmatterError as exc:
        return NoteVerdict(_frontmatter_error_status(str(exc)), relpath, reason=str(exc))
    except (json.JSONDecodeError, ValueError) as exc:
        return NoteVerdict(REFUSED_INVALID_JSON, relpath, reason=str(exc))
    try:
        record = Record.from_dict(payload)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return NoteVerdict(REFUSED_INVALID_SCHEMA, relpath, reason=str(exc))
    problems = validate_record(record)
    if problems:
        return NoteVerdict(REFUSED_INVALID_RECORD, relpath, reason="; ".join(problems))
    return NoteVerdict(LOADED, relpath, record=record)


def _identity_verdict(record: Record, relpath: str) -> NoteVerdict | None:
    """Steps 10 + 11: spoof check and scope-directory match. Symmetric to
    R2 mirror's `_require_canon_at` and R1 D-18's mis-scope refusal."""
    try:
        derived = derive_note_name(record)
    except VaultError as exc:
        return NoteVerdict(REFUSED_INVALID_RECORD, relpath, reason=str(exc))
    norm_rel = relpath.replace("\\", "/")
    if os.path.normcase(derived) != os.path.normcase(norm_rel):
        return NoteVerdict(
            REFUSED_SPOOF, relpath,
            reason=f"derived {derived!r} != on-disk {norm_rel!r}")
    parts = norm_rel.split("/")
    if (len(parts) >= 1
            and os.path.normcase(parts[0]) != os.path.normcase(record.scope)):
        return NoteVerdict(
            REFUSED_MIS_SCOPE, relpath,
            reason=f"file under {parts[0]!r} but record.scope {record.scope!r}")
    return None


def classify_vault_entry(root: str, relpath: str, text: object) -> NoteVerdict:
    """Pure per-entry classifier: no IO. `text` is what read_text returned
    (str, bytes, or None from an absent file)."""
    pre = _pre_containment_verdict(root, relpath)
    if pre is not None:
        return pre
    if text is None:
        return NoteVerdict(SKIPPED_ABSENT, relpath)
    enc = _encoding_verdict(text, relpath)
    if enc is not None:
        return enc
    normalized = _normalize_newlines(text)  # type: ignore[arg-type]
    verdict = _parse_and_reconstruct(normalized, relpath)
    if verdict.status != LOADED:
        return verdict
    ident = _identity_verdict(verdict.record, relpath)  # type: ignore[arg-type]
    if ident is not None:
        return ident
    return verdict


def read_note_at(root: str, relpath: str, *, read_text) -> NoteVerdict:
    """Single-note reader. Runs containment before touching read_text (so a
    disallowed relpath never triggers a call to the injected callable)."""
    pre = _pre_containment_verdict(root, relpath)
    if pre is not None:
        return pre
    try:
        text = read_text(_abs(root, relpath))
    except Exception as exc:  # noqa: BLE001 -- totality guarantee
        return NoteVerdict(SKIPPED_ABSENT, relpath, reason=f"read_text raised: {exc}")
    return classify_vault_entry(root, relpath, text)


def _dedupe_verdicts(verdicts: list[NoteVerdict]) -> list[NoteVerdict]:
    """First-wins dedupe on `record_key` across LOADED verdicts; subsequent
    LOADED for the same key becomes REFUSED_DUPLICATE_KEY. Case-fold
    filenames may target the same derived name via sha256-truncation collision;
    that is REFUSED_NAME_COLLISION."""
    out: list[NoteVerdict] = []
    seen_keys: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    for v in verdicts:
        if v.status != LOADED or v.record is None:
            out.append(v)
            continue
        key = record_key(v.record)
        name_nc = os.path.normcase(v.relpath.replace("\\", "/"))
        if key in seen_keys:
            out.append(NoteVerdict(
                REFUSED_DUPLICATE_KEY, v.relpath, record=v.record,
                reason=f"key {key!r} first at {seen_keys[key]!r}"))
            continue
        if name_nc in seen_names:
            out.append(NoteVerdict(
                REFUSED_NAME_COLLISION, v.relpath, record=v.record,
                reason=f"name {name_nc!r} first at {seen_names[name_nc]!r}"))
            continue
        seen_keys[key] = v.relpath
        seen_names[name_nc] = v.relpath
        out.append(v)
    return out


def classify_vault(root: str, *, list_dir, read_text) -> ReadPlan:
    """Phase 1: list, classify, dedupe. No pool assembly yet."""
    entries = sorted(list_dir(root))
    verdicts: list[NoteVerdict] = []
    for relpath in entries:
        verdicts.append(read_note_at(root, relpath, read_text=read_text))
    return ReadPlan(root=root, verdicts=tuple(_dedupe_verdicts(verdicts)))


def load_from_plan(plan: ReadPlan) -> VaultReadResult:
    """Phase 2: fold verdicts into pool, refusals, skipped, counts."""
    pool: list[Record] = []
    refusals: list[NoteVerdict] = []
    skipped: list[NoteVerdict] = []
    counts: dict[str, int] = {}
    for v in plan.verdicts:
        counts[v.status] = counts.get(v.status, 0) + 1
        if v.status == LOADED and v.record is not None:
            pool.append(v.record)
        elif v.status in OK_STATUSES:
            skipped.append(v)
        else:
            refusals.append(v)
    ok = not refusals
    return VaultReadResult(
        pool=tuple(pool), refusals=tuple(refusals), skipped=tuple(skipped),
        counts=counts, ok=ok)


def read_vault(root: str, *, list_dir, read_text) -> VaultReadResult:
    """Whole-vault read: classify then load. Never raises."""
    return load_from_plan(classify_vault(root, list_dir=list_dir, read_text=read_text))


def read_vault_scope(root: str, scope: str, *,
                     list_dir, read_text) -> VaultReadResult:
    """One scope's directory only. An unknown scope string is a wiring fault
    (ValueError); a scope directory that is absent is a runtime data condition
    the reader tolerates by returning an empty result (D-87 split)."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {SCOPES!r}")
    scope_prefix = scope + "/"

    def _scoped_list(path):
        return [r for r in list_dir(path)
                if r.replace("\\", "/").startswith(scope_prefix)]
    return read_vault(root, list_dir=_scoped_list, read_text=read_text)


def read_exit_code(result: VaultReadResult) -> int:
    """0 iff result.ok, 1 on any refusal. Mirrors drift_exit_code and
    reconcile_exit_code so a build can gate on the read leg the same way."""
    return 0 if result.ok else 1
