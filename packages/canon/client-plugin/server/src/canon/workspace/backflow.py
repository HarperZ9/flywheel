"""backflow.py -- edits made inside a canon region come back as proposals.

When a person or another tool edits the region canon wrote into an instruction
file, overwriting it on the next switch would lose that work. `find_edits`
reads the region on disk against what canon wrote (the render ledger):

- A region equal to any render canon remembers writing to this surface, from
  any checkout, is stale, not edited, and has no edits. So is an empty region
  (a fresh opt-in marker pair).
- Otherwise the base is the closest of this checkout's last render and the
  remembered renders, so a file one render behind, or restored by a branch
  switch, is read against the render it came from.
- A block that changed, appeared or disappeared becomes a proposed personality
  block (a disappearance proposes retiring it), unless another project or
  global owns it: that edit is kept in the note, naming the owner, and never
  proposed under this project. An edited brief is read back line by line
  (backflow_brief). A changed sentinel ordinal or supersedes link, a changed
  brief heading, and every line no rule maps go into one proposed memory
  record, so the text is kept. A region whose grammar the edit broke keeps its
  changed lines the same way.

With no base (canon never wrote this file in this checkout), only additions and
changes count: an absent block says nothing when canon never put it there.

Proposals go through the same path as imports: scrubbed, validated, written as
proposed rows with an origin naming the surface, the file digest, the line, the
rule, the render the edit was read against and the accepted record it was
built from. An edit already accepted is skipped; one rejected against the same
render is skipped, and proposed again once a later render stands. `switch`
refuses to overwrite a region while any of its edits is undecided.
"""
from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, replace

from canon.layering import is_current
from canon.region import RegionError, extract_region
from canon.schema import KIND_EPISODIC_MEMORY, KIND_PERSONALITY_BLOCK, Record, Temporal
from canon.textblock import IngestRefused, ingest_region
from canon.workspace import authoring
from canon.workspace.backflow_brief import Edit, brief_edits
from canon.workspace.import_write import seen_before
from canon.workspace.rows import STATE_PROPOSED
from canon.workspace.scrub import scrub_value
from canon.workspace.store import ProjectStore, record_digest

BRIEF_BLOCK_ID = "canon-workspace-brief"
HARNESS = "canon-drift"
_PREFIX = {"work-item": "task", "environment-constraint": "constraint",
           "episodic-memory": "note", "personality-block": "block"}


@dataclass(frozen=True, slots=True)
class RegionEdits:
    edits: tuple[Edit, ...]
    parse_error: str | None


def _wrap(interior: str) -> str:
    return f"<!-- canon:begin scope=workspace -->\n{interior}<!-- canon:end -->\n"


def _sentinel_lines(host: str) -> dict[str, int]:
    """Block id to the file line number of its sentinel."""
    found = {}
    for number, line in enumerate(host.replace("\r\n", "\n").split("\n"), start=1):
        if line.startswith('<!-- canon:block id="'):
            found[line.split('"', 2)[1]] = number
    return found


def _link(block: Record) -> tuple:
    sup = block.temporal.supersedes if block.temporal is not None else None
    return block.provenance.create_ord, sup


def _block_edits(actual: list[Record], base: list[Record], lines: dict[str, int],
                 has_base: bool, owner_of) -> tuple[list[Edit], list[str]]:
    was = {b.id: b for b in base if b.id != BRIEF_BLOCK_ID}
    now = {b.id: b for b in actual if b.id != BRIEF_BLOCK_ID}
    edits, notes = [], []
    for rid, block in now.items():
        prior = was.get(rid)
        if prior is not None and block.data == prior.data:
            if _link(block) != _link(prior):
                notes.append(f"block {rid}: ord and sup changed from {_link(prior)} "
                             f"to {_link(block)}")
            continue
        owner = owner_of(rid) if prior is not None else None
        if owner:
            notes.append(f"block {rid} belongs to {owner}; edit it there. Edited text: "
                         f"{block.data['title']}: {block.data['body']}")
            continue
        edits.append(Edit("new-block" if prior is None else "edited-block",
                          KIND_PERSONALITY_BLOCK, rid, dict(block.data), lines.get(rid, 0)))
    for rid, block in was.items() if has_base else ():
        if rid in now:
            continue
        if owner_of(rid):
            notes.append(f"removed block {rid}, which belongs to {owner_of(rid)}; it "
                         "renders again on the next switch")
        else:
            edits.append(Edit("removed-block", KIND_PERSONALITY_BLOCK, rid,
                              dict(block.data), 0, retire=True))
    return edits, notes


def _note(lines: list[str], line: int, rule: str = "unmapped-edit") -> Edit:
    return Edit(rule, KIND_EPISODIC_MEMORY, None,
                {"layer": "L0", "text": "\n".join(lines), "source_ids": []}, line)


def _unparseable(actual: str, base: str, offset: int) -> Edit:
    changed = [line[2:].strip() for line in difflib.ndiff(base.split("\n"), actual.split("\n"))
               if line.startswith("+ ") and line[2:].strip()]
    return _note(changed or [actual], offset, "unparseable-region")


def _closest(actual: str, candidates: list[str]) -> str:
    lines = actual.split("\n")
    return max(candidates, key=lambda c: difflib.SequenceMatcher(
        None, c.split("\n"), lines, autojunk=False).ratio())


def _owner_function(owners: dict | None, own: str | None):
    table = owners or {}
    return lambda rid: (table.get(rid) if table.get(rid) not in (None, own) else None)


def find_edits(host: str, base_interior: str | None, new_interior: str,
               records: list[Record], *, known: list[str] = (), owners: dict | None = None,
               own: str | None = None) -> RegionEdits:
    """The in-place edits in `host`'s region, read against the closest render
    canon wrote. `known` holds the renders canon remembers for this surface;
    `owners` maps a rendered block id to the project or `global` owning it."""
    region = extract_region(host)
    actual = region.inner.replace("\r\n", "\n")
    has_base = base_interior is not None
    if not actual.strip() or actual in (new_interior, base_interior) or actual in known:
        return RegionEdits((), None)
    candidates = ([base_interior] if has_base else []) + list(known)
    base = _closest(actual, candidates) if candidates else new_interior
    offset = region.prefix.replace("\r\n", "\n").count("\n") + 1
    try:
        now_blocks = ingest_region(host)
        was_blocks = ingest_region(_wrap(base))
    except (IngestRefused, RegionError) as exc:
        return RegionEdits((_unparseable(actual, base, offset),), str(exc))
    lines = _sentinel_lines(host)
    edits, notes = _block_edits(now_blocks, was_blocks, lines, has_base,
                                _owner_function(owners, own))
    unmapped = [(lines.get(BRIEF_BLOCK_ID, offset), n) for n in notes]
    now_brief = next((b for b in now_blocks if b.id == BRIEF_BLOCK_ID), None)
    was_brief = next((b for b in was_blocks if b.id == BRIEF_BLOCK_ID), None)
    if now_brief is not None:
        if was_brief is not None and now_brief.data["title"] != was_brief.data["title"]:
            unmapped.append((lines.get(BRIEF_BLOCK_ID, 0) + 1,
                             f"brief heading: {now_brief.data['title']}"))
        more, loose = brief_edits(now_brief.data["body"],
                                  was_brief.data["body"] if was_brief else "",
                                  lines.get(BRIEF_BLOCK_ID, 0) + 2, records,
                                  has_base=has_base and was_brief is not None)
        edits += more
        unmapped += loose
    if unmapped:
        edits.append(_note([t for _, t in unmapped], unmapped[0][0]))
    return RegionEdits(tuple(edits), None)


def _edit_id(edit: Edit, surface: str) -> str:
    if edit.rid:
        return edit.rid
    digest = hashlib.sha256(f"{surface}\n{edit.rule}\n{edit.data}".encode("utf-8"))
    return f"drift-{_PREFIX[edit.kind]}-{digest.hexdigest()[:12]}"


def _record(edit: Edit, surface: str, ordinal: int, hits: dict) -> Record:
    data = scrub_value(edit.data, hits)
    record = authoring.build(edit.kind, _edit_id(edit, surface), data, ordinal,
                             harness=HARNESS, native_id=f"drift:{surface}:{edit.line}")
    if edit.retire:
        record = replace(record, temporal=Temporal(valid_until=ordinal, supersedes=None))
    return record


def propose_edits(store: ProjectStore, edits: RegionEdits, *, surface: str,
                  file_sha256: str, dry_run: bool = False,
                  base_render: int | None = None) -> dict:
    """Write each edit as a proposed record unless the same content was already
    accepted, or rejected against the same render. Returns what was proposed and
    what was decided before."""
    accepted, rejected = seen_before(store)
    hits: dict[str, int] = {}
    ordinal = store.next_ord()
    proposed, decided = [], []
    for edit in edits.edits:
        kept = accepted.get(edit.rid).provenance.create_ord if edit.rid in accepted else None
        record = _record(edit, surface, kept or ordinal, hits)
        ordinal += 1
        content = authoring.content_hash(record.kind, record.data) + (
            ":retire" if edit.retire else "")
        entry = {"id": record.id, "kind": record.kind, "rule": edit.rule, "line": edit.line}
        prior = accepted.get(record.id)
        same = prior is not None and prior.data == record.data and \
            (not is_current(prior)) == edit.retire
        if (record.id, content, base_render) in rejected or same:
            decided.append({**entry, "rejected": not same})
            continue
        if not dry_run:
            origin = {"importer": "drift", "source": surface, "source_sha256": file_sha256,
                      "line": edit.line, "rule": edit.rule, "content_sha256": content,
                      "base_render": base_render,
                      "base_record_sha256": record_digest(prior) if prior else None}
            store.put(record, state=STATE_PROPOSED, origin=origin, action="pull")
        proposed.append(entry)
    return {"surface": surface, "proposed": proposed, "already_decided": decided,
            "parse_error": edits.parse_error, "secrets_redacted": hits, "dry_run": dry_run}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pending_edits(store: ProjectStore, plan, *, dry_run: bool) -> dict | None:
    """Read back the in-place edits in a switch plan's current file and propose
    them. None when the plan has no existing file or its region has no edits."""
    from canon.workspace.ledger import known_renders, last_render
    if plan.surface is None or plan.old_text is None:
        return None
    rel = plan.surface.relative_path
    entry = last_render(store, rel, store.identity.checkout)
    owners = {**plan.owners, **(entry.owners if entry else {})}
    edits = find_edits(plan.old_text, entry.interior if entry else None, plan.interior,
                       store.records(), known=known_renders(store, rel), owners=owners,
                       own=store.project_id)
    if not edits.edits:
        return None
    return propose_edits(store, edits, surface=rel, file_sha256=_sha(plan.old_text),
                         dry_run=dry_run, base_render=entry.seq if entry else None)
