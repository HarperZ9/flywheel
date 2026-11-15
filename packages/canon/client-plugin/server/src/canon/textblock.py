"""textblock.py -- the record<->text layer of the R0 surface.

render_region projects a scope-homogeneous list of personality-block records
into the canon region interior; ingest_region reads records back out of a
managed file (it owns the extract_region call and speaks the same grammar).

One line model, shared by both directions: normalize CRLF->LF, then split on
'\n'; a bare '\r' that survives is illegal. render refuses to emit a bare CR and
ingest refuses a residual bare CR, which closes the "a buried CR joins the next
sentinel into a body line" injection the design flagged -- and leaves no CR->LF
content drop to declare, because a CRLF host terminator is the only CR ever
normalized and it is not content.

render's refusal set is a strict superset of ingest's parse constraints: every
record render emits re-ingests. render refuses, up front, any record it cannot
represent -- non-dict data, a missing provenance, a non-int or negative
create_ord, a duplicate id, or an empty / CR-bearing / marker-bearing id or sup
-- rather than emit text the ingest leg would then reject. ingest additionally
refuses a sentinel whose id/sup carries a marker token (its regex excludes '<'
and '>', so '-->' cannot appear). Both fail loudly rather than silently mangle.

W1 extends the grammar (canon.textblock/v1) with an optional `applies`
attribute on the sentinel and a generated `Applies to:` line; see
textblock_scope.py. A region with no scoped block is byte-identical to v0.
"""
from __future__ import annotations

import hashlib
import json
import re

from canon.region import extract_region
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record, Temporal
from canon.textblock_scope import attribute, check_applies, strip_visible, visible_line
from canon.validator import validate_record

RESERVED_PREFIX = "<!-- canon:"
_TITLE_PREFIX = "## "
_HARNESS = "canon-text"

_BLOCK_RE = re.compile(
    r'^<!-- canon:block id="([^"<>\n]+)"'
    r'(?: ord="([0-9]+)")?'
    r'(?: sup="([^"<>\n]+)")?'
    r'(?: applies="([^"<>\n]+)")? -->$'
)


class RenderRefused(Exception):
    """A record cannot be represented as text without loss or ambiguity, so
    render refuses the whole batch rather than emit a corrupt region."""

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(f"{record_id!r}: {reason}")
        self.record_id = record_id
        self.reason = reason


class IngestRefused(Exception):
    """The region interior is not a well-formed, unambiguous block sequence, so
    ingest refuses rather than guess."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def recompute_source_hash(title: str, body: str,
                          applies: list[str] | None = None) -> str:
    """The canonical content hash for a personality block. Injective on
    (title, body) via the keyed JSON envelope, stable across processes (sorted
    keys, no wall clock), and a locked format contract: layering tie-breaks read
    it, so its bytes must not drift. A W1 scope joins the envelope only when a
    block has one, so every block without a scope keeps its hash."""
    envelope: dict = {"v": 1, "title": title, "body": body}
    if applies:
        envelope["applies_to"] = list(applies)
    payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---- render -------------------------------------------------------------------

def render_region(records: list[Record], scope: str) -> str:
    """Render records into the region interior for `scope`. Refuses (loudly, no
    partial output) on the first record it cannot represent. Empty input renders
    the empty region."""
    seen: set[str] = set()
    parts: list[str] = []
    for rec in records:
        _check_render_record(rec, scope, seen)
        parts.append(_render_block(rec))
    return "".join(parts)


def _check_render_record(rec: Record, scope: str, seen: set[str]) -> None:
    rid = rec.id
    if rec.kind != KIND_PERSONALITY_BLOCK:
        raise RenderRefused(rid, f"kind {rec.kind!r} is not personality-block")
    if rec.scope != scope:
        raise RenderRefused(rid, f"scope {rec.scope!r} != target {scope!r}")
    t = rec.temporal
    if t is not None and t.valid_until is not None:
        raise RenderRefused(rid, "record is non-current (valid_until set)")
    if not isinstance(rec.data, dict):
        raise RenderRefused(rid, f"data is not a dict: {type(rec.data).__name__}")
    extra = set(rec.data) - {"title", "body", "applies_to"}
    if extra:
        raise RenderRefused(rid, f"unexpected data keys {sorted(extra)}")
    if "applies_to" in rec.data:
        reason = check_applies(rec.data["applies_to"])
        if reason:
            raise RenderRefused(rid, reason)
    title, body = rec.data.get("title"), rec.data.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        raise RenderRefused(rid, "title and body must be strings")
    if not title:
        raise RenderRefused(rid, "empty title")
    if not body:
        raise RenderRefused(rid, "empty body")
    if "\n" in title:
        raise RenderRefused(rid, "title spans multiple lines")
    if "\r" in title or "\r" in body:
        raise RenderRefused(rid, "bare CR in title or body")
    for line in (title + "\n" + body).split("\n"):
        if line.lstrip().startswith(RESERVED_PREFIX):
            raise RenderRefused(rid, f"reserved marker line in content: {line!r}")
    _check_token(rid, "id", rid)
    sup = t.supersedes if t is not None else None
    if sup is not None:
        _check_token(rid, "sup", sup)
    if rec.provenance is None:
        raise RenderRefused(rid, "record has no provenance")
    ord_ = rec.provenance.create_ord
    if ord_ is not None and (not isinstance(ord_, int) or isinstance(ord_, bool)):
        raise RenderRefused(rid, f"create_ord must be an int: {ord_!r}")
    if ord_ is not None and ord_ < 0:
        raise RenderRefused(rid, f"negative create_ord {ord_}")
    if rid in seen:
        raise RenderRefused(rid, "duplicate id in batch")
    seen.add(rid)


def _check_token(rid: str, name: str, value: str) -> None:
    if value == "":
        raise RenderRefused(rid, f"empty {name}")
    for ch in ('"', "<", ">", "\n", "\r"):
        if ch in value:
            raise RenderRefused(rid, f"illegal character in {name}: {value!r}")


def _render_block(rec: Record) -> str:
    p = rec.provenance
    sup = rec.temporal.supersedes if rec.temporal is not None else None
    head = f'<!-- canon:block id="{rec.id}"'
    if p.create_ord is not None:
        head += f' ord="{p.create_ord}"'
    if sup is not None:
        head += f' sup="{sup}"'
    body = rec.data["body"]
    globs = rec.data.get("applies_to")
    if globs:
        head += attribute(globs)
        body = visible_line(globs) + "\n" + body
    head += " -->"
    return f'{head}\n{_TITLE_PREFIX}{rec.data["title"]}\n{body}\n'


# ---- ingest -------------------------------------------------------------------

def ingest_region(file_text: str) -> list[Record]:
    """Read records from a managed file. Returns [] when the file has no region
    (off-limits) or the region is empty. Refuses (IngestRefused / RegionError)
    on a residual bare CR or any malformed interior."""
    s = extract_region(file_text)
    if not s.present:
        return []
    inner = s.inner.replace("\r\n", "\n")
    if "\r" in inner:
        raise IngestRefused("residual bare CR in region interior")
    return _parse_inner(inner, s.scope)


def _parse_inner(inner: str, scope: str | None) -> list[Record]:
    if inner == "":
        return []
    lines = inner.split("\n")
    sentinels = [i for i, ln in enumerate(lines) if _BLOCK_RE.match(ln)]
    _guard_reserved_lines(lines, set(sentinels))
    if not sentinels:
        if all(ln.strip(" \t") == "" for ln in lines):
            return []
        raise IngestRefused("region has content but no block sentinel")
    _guard_prefix_whitespace(lines, sentinels[0])
    records: list[Record] = []
    ids: set[str] = set()
    for k, si in enumerate(sentinels):
        end = sentinels[k + 1] if k + 1 < len(sentinels) else len(lines) - 1
        rec = _build_block(lines, si, end, scope)
        if rec.id in ids:
            raise IngestRefused(f"duplicate block id {rec.id!r}")
        ids.add(rec.id)
        records.append(rec)
    return records


def _guard_reserved_lines(lines: list[str], sentinel_set: set[int]) -> None:
    for i, ln in enumerate(lines):
        if i in sentinel_set:
            continue
        if ln.lstrip().startswith(RESERVED_PREFIX):
            raise IngestRefused(
                f"reserved marker line is not a valid sentinel: {ln!r}")


def _guard_prefix_whitespace(lines: list[str], first: int) -> None:
    for ln in lines[:first]:
        if ln.strip(" \t") != "":
            raise IngestRefused(
                f"non-whitespace content before first sentinel: {ln!r}")


def _build_block(lines: list[str], si: int, end: int,
                 scope: str | None) -> Record:
    m = _BLOCK_RE.match(lines[si])
    assert m is not None  # si came from the sentinel scan
    bid, ord_s, sup, applies = m.group(1), m.group(2), m.group(3), m.group(4)
    if end <= si + 1:
        raise IngestRefused(f"block {bid!r} has no title line")
    title_line = lines[si + 1]
    if not title_line.startswith(_TITLE_PREFIX):
        raise IngestRefused(
            f"block {bid!r}: line after sentinel is not a '## ' title: "
            f"{title_line!r}")
    if end <= si + 2:
        raise IngestRefused(f"block {bid!r} has no body")
    title = title_line[len(_TITLE_PREFIX):]
    globs = applies.split("|") if applies is not None else None
    body_lines = lines[si + 2:end]
    if globs is not None:
        try:
            body_lines = strip_visible(bid, body_lines, globs)
        except ValueError as exc:
            raise IngestRefused(str(exc)) from exc
    body = "\n".join(body_lines)
    ord_ = int(ord_s) if ord_s is not None else None
    rec = _assemble(bid, title, body, ord_, sup, scope, globs)
    problems = validate_record(rec)
    if problems:
        raise IngestRefused(f"block {bid!r} failed validation: {problems}")
    return rec


def _assemble(bid: str, title: str, body: str, create_ord: int | None,
              sup: str | None, scope: str | None,
              applies: list[str] | None = None) -> Record:
    prov = Provenance(
        harness=_HARNESS,
        source_hash=recompute_source_hash(title, body, applies),
        native_id=f"{_HARNESS}:{scope}/{bid}",
        session_id=None,
        create_ord=create_ord,
        create_time=None,
        model_slug=None)
    temporal = (Temporal(valid_until=None, supersedes=sup)
                if sup is not None else None)
    data = {"title": title, "body": body}
    if applies:
        data["applies_to"] = list(applies)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=bid, scope=scope,
                  data=data, provenance=prov, temporal=temporal)


def canonicalize_record(rec: Record) -> Record:
    """The record ingest would produce from render([rec]): declared drops zeroed
    (harness->canon-text, native_id rebound, model_slug/create_time/session_id
    None), carried fields kept, temporal collapsed to a bare supersedes link or
    None. Built through _assemble so it can never drift from the ingest path."""
    sup = rec.temporal.supersedes if rec.temporal is not None else None
    return _assemble(rec.id, rec.data["title"], rec.data["body"],
                     rec.provenance.create_ord, sup, rec.scope,
                     rec.data.get("applies_to"))
