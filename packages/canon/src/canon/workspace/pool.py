"""pool.py -- the record pool one project's render may read.

The renderers (surface, handoff, switch) never open a store file themselves.
They take the pool this module assembles, so the isolation rule lives in one
place: global rows, the project's own accepted rows, and the accepted rows of
any other project the caller named. A proposed row is never in a pool.

A declared foreign project is read, not merged. When a foreign personality
block shares an id with one of this project's blocks, layering would let one
override the other silently, so the pool refuses instead.
"""
from __future__ import annotations

from dataclasses import dataclass

from canon.layering import is_current
from canon.schema import KIND_PERSONALITY_BLOCK, Record
from canon.workspace.store import IsolationError, ProjectStore


def visible_records(store: ProjectStore, *,
                    include_projects: tuple[str, ...] = ()
                    ) -> list[tuple[str | None, Record]]:
    """The records a render or a brief for `store`'s project may read, each
    tagged with the project it belongs to (None for global). Another project's
    records appear only when its id is named in `include_projects`."""
    seen: list[tuple[str | None, Record]] = [(None, r.record)
                                             for r in store.global_rows()]
    seen += [(store.project_id, rec) for rec in store.records()]
    for pid in sorted(set(include_projects)):
        if pid == store.project_id:
            continue
        foreign = ProjectStore(store.root, pid)
        seen += [(pid, rec) for rec in foreign.records()]
    return seen


@dataclass(frozen=True, slots=True)
class TaggedRecord:
    """A record and the project it belongs to (None for a global record)."""

    project_id: str | None
    record: Record


def project_pool(store: ProjectStore, *,
                 include_projects: tuple[str, ...] = ()) -> list[TaggedRecord]:
    """Every record a render for `store`'s project may read, tagged."""
    tagged = [TaggedRecord(pid, rec) for pid, rec in
              visible_records(store, include_projects=include_projects)]
    _refuse_block_collisions(tagged, store.project_id)
    return tagged


def block_pool(pool: list[TaggedRecord]) -> list[Record]:
    """The personality blocks of a pool, the input the surface renderer takes."""
    return [t.record for t in pool if t.record.kind == KIND_PERSONALITY_BLOCK]


def _refuse_block_collisions(tagged: list[TaggedRecord], own: str) -> None:
    owners: dict[tuple[str, str], set[str | None]] = {}
    for item in tagged:
        rec = item.record
        if rec.kind != KIND_PERSONALITY_BLOCK or not is_current(rec):
            continue  # a retired copy renders nothing, so it overrides nothing
        owners.setdefault((rec.scope, rec.id), set()).add(item.project_id)
    for (scope, rid), projects in sorted(owners.items()):
        if len(projects - {None}) > 1:
            others = sorted(p for p in projects if p not in (None, own))
            raise IsolationError(
                f"block {scope}/{rid} is carried by this project and by "
                f"declared project(s) {others}; refusing to let one override "
                "the other")
