"""layering.py -- resolve the canonical block set to an effective set per scope.

The operator's personality model is one canonical block set with per-scope
overrides layered at render time. This module is that layering, and only that:
given a pool of personality-block records tagged `global` or `workspace`, it
computes the effective set a renderer would emit for a target scope.

The rules, in order:

  1. Current only. A record whose temporal block sets `valid_until` has been
     superseded and is excluded. A record with no temporal block, or one whose
     `valid_until` is None, is current.
  2. Override by id. Blocks are keyed by their record id. A workspace block
     with the same id as a global block overrides it; a workspace-only id is
     added; a global-only id is always present.
  3. Scope containment. A render at `global` scope sees only global blocks --
     workspace overrides never leak upward. A render at `workspace` scope sees
     global blocks overlaid by workspace blocks.
  4. Deterministic order. The effective list is ordered by the clock-free
     `create_ord` ascending, then by id, so a rebuild from the same pool is
     byte-identical. Records with no `create_ord` sort after those that have
     one (an ordinal is the norm; its absence is the exception).

Only personality-block records participate. Other kinds accumulate in a store;
they are not a canon that overrides itself, so passing them in is a caller
error, reported rather than silently ignored.
"""
from __future__ import annotations

from .schema import (
    KIND_PERSONALITY_BLOCK,
    SCOPE_GLOBAL,
    SCOPE_WORKSPACE,
    SCOPES,
    Record,
)


class LayeringError(ValueError):
    """Raised when the pool contains a record layering cannot place."""


def is_current(rec: Record) -> bool:
    """A record is current unless its temporal block sets a `valid_until`."""
    return rec.temporal is None or rec.temporal.valid_until is None


def _sort_key(rec: Record) -> tuple:
    ord_ = rec.provenance.create_ord
    # None sorts last: (1, 0) after every (0, ord). id is the stable tie-break.
    if ord_ is None:
        return (1, 0, rec.id)
    return (0, ord_, rec.id)


def _pick_current(records: list[Record]) -> Record:
    """From records sharing one (scope, id), return the surviving current one.

    Prefers a current record; if several are current (which should not happen
    for a well-formed pool), the highest create_ord wins so the newest write
    is authoritative. A tie on create_ord breaks on source_hash, so the choice
    is independent of the pool's ordering rather than "whichever came first in
    the list" (id is constant within this group and cannot break the tie). If
    none is current, the newest superseded record stands in, so an
    all-superseded id still resolves deterministically rather than vanishing."""
    current = [r for r in records if is_current(r)]
    pool = current if current else records

    def newest_key(r: Record) -> tuple:
        ord_ = r.provenance.create_ord
        ranked = (0, ord_) if ord_ is not None else (-1, 0)
        return (*ranked, r.provenance.source_hash)

    return max(pool, key=newest_key)


def resolve_blocks(records: list[Record], target_scope: str) -> list[Record]:
    """Resolve the pool to the effective block list for `target_scope`.

    See the module docstring for the rules. Raises LayeringError on an unknown
    scope or a non-personality-block record in the pool."""
    if target_scope not in SCOPES:
        raise LayeringError(f"unknown target scope {target_scope!r}; expected one of {list(SCOPES)}")

    for rec in records:
        if rec.kind != KIND_PERSONALITY_BLOCK:
            raise LayeringError(
                f"layering accepts only {KIND_PERSONALITY_BLOCK!r} records; "
                f"got a {rec.kind!r} (id {rec.id!r})"
            )
        if rec.scope not in SCOPES:
            raise LayeringError(f"record {rec.id!r} has unknown scope {rec.scope!r}")

    # Which scopes contribute, in overlay order (later overrides earlier).
    if target_scope == SCOPE_GLOBAL:
        contributing = (SCOPE_GLOBAL,)
    else:
        contributing = (SCOPE_GLOBAL, SCOPE_WORKSPACE)

    # Collapse each (scope, id) group to its surviving record first, so a
    # superseded duplicate within one scope never shadows the current one.
    by_scope_id: dict[tuple[str, str], list[Record]] = {}
    for rec in records:
        by_scope_id.setdefault((rec.scope, rec.id), []).append(rec)
    survivor: dict[tuple[str, str], Record] = {
        key: _pick_current(group) for key, group in by_scope_id.items()
    }

    # Overlay scopes in order; a later scope's current block replaces an
    # earlier one's. A non-current survivor -- every record for that
    # (scope, id) is superseded -- simply does not participate. There is no
    # tombstone kind, so a retired workspace override falls back to the global
    # block of the same id rather than suppressing it.
    effective: dict[str, Record] = {}
    for scope in contributing:
        for (rec_scope, rec_id), rec in survivor.items():
            if rec_scope != scope:
                continue
            if not is_current(rec):
                continue
            effective[rec_id] = rec

    return sorted(effective.values(), key=_sort_key)
