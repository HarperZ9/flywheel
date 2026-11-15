"""backends/mneme.py -- MnemeBackend: the temporal home for memory records.

mneme is canon's memory fact-engine of record. This adapter maps the two memory
kinds -- episodic-memory and synthesized-persona-l3 -- onto an injected mneme
Store handle, so canon stays self-contained: it imports no mneme package and
speaks only to a duck-typed handle with mneme's surface (proved against a fake
that mirrors the source). It keeps temporal history: a supersede is recorded as
mneme's supersede() between two present rows and read back from each row's
valid_until and superseded_by.

Mappings. canon `scope` occupies mneme's `user` column (canon has no separate
user concept at F1; memory ids are unique, so no cross-scope collision).
provenance.session_id maps to mneme's `session`. The data payload
(layer/text/source_ids/extractor/criterion) maps field-for-field.

Declared drops. mneme models memory, not a graph, so it refuses every
non-memory kind (`arbitrary-kind`) and holds no typed relations (`relations`).
And its rows carry their own provenance columns -- a content hash, a created
ordinal -- not canon's full receipt, so a foreign provenance (a `source_hash`,
`create_ord`, or `harness` not mneme's own) is normalized to the mneme-derived
shape on read (`foreign-provenance`). Content, scope, session, and the
supersession pairing round-trip; a foreign provenance receipt does not, and a
caller-supplied valid_until is refused at put() rather than stored, because
mneme owns the ordinal clock (see _require_storable_temporal).
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_SYNTHESIZED_PERSONA_L3,
    PERSONA_LAYER,
    SCOPE_GLOBAL,
    Provenance,
    Record,
    Temporal,
)

from .base import (
    CAP_ARBITRARY_KIND,
    CAP_FOREIGN_PROVENANCE,
    CAP_RELATIONS,
    BackendError,
    DropError,
    MissingSupersedeTarget,
    guard_put,
    split_key,
)

_MEMORY_KINDS = frozenset({KIND_EPISODIC_MEMORY, KIND_SYNTHESIZED_PERSONA_L3})


class MnemeStore(Protocol):
    """The slice of mneme's Store surface this adapter uses. Any object with
    these methods works; the real mneme.Store satisfies it, as does the test
    fake."""

    def add_memory(self, memory_id: str, layer: str, text: str,
                   source_ids: Any, extractor: str, criterion: str,
                   session: "str | None" = None, user: str = "") -> Any: ...

    def memory(self, memory_id: str) -> Any: ...

    def memories(self, *, include_superseded: bool = False) -> Any: ...

    def supersede(self, old_id: str, new_id: str, reason: str = "") -> Any: ...


class MnemeBackend:
    name = "mneme"

    def __init__(self, store: MnemeStore) -> None:
        self._store = store

    def supported_kinds(self) -> frozenset[str]:
        return _MEMORY_KINDS

    def declared_drops(self) -> frozenset[str]:
        return frozenset({CAP_ARBITRARY_KIND, CAP_RELATIONS,
                          CAP_FOREIGN_PROVENANCE})

    def flatten(self, record: Record) -> Record:
        # mneme keeps the supersedes link but assigns valid_until from its own
        # clock, so a caller-supplied valid_until is the one removable field.
        # Strip only that; keep supersedes.
        t = record.temporal
        if t is None or t.valid_until is None:
            return record
        if t.supersedes is None:
            return record.with_temporal(None)
        return record.with_temporal(Temporal(valid_until=None, supersedes=t.supersedes))

    def put(self, record: Record) -> None:
        guard_put(self, record)
        self._require_storable_temporal(record)
        d = record.data
        try:
            self._store.add_memory(
                record.id, d["layer"], d["text"], d["source_ids"],
                d.get("extractor", ""), d.get("criterion", ""),
                session=record.provenance.session_id, user=record.scope)
        except ValueError as e:
            raise BackendError(f"mneme refused record {record.id!r}: {e}") from e
        supersedes = record.temporal.supersedes if record.temporal else None
        if supersedes:
            self._store.supersede(supersedes, record.id)

    def _require_storable_temporal(self, record: Record) -> None:
        """Raise before any write if mneme cannot store the record's temporal
        block. A caller-supplied valid_until is refused (mneme owns the ordinal
        clock); a supersedes pointing at a row that is not present and current is
        refused (mneme links only between two present rows). Neither loss is
        silent; the first is opt-in via flatten(), the second needs the target
        stored first."""
        t = record.temporal
        if t is None:
            return
        if t.valid_until is not None:
            raise DropError(
                f"mneme assigns supersession ordinals from its own clock; record "
                f"{record.id!r} carries valid_until={t.valid_until}, which mneme "
                f"cannot store as given -- flatten() to strip it (the supersedes "
                f"link is kept).")
        if t.supersedes is not None:
            target = self._store.memory(t.supersedes)
            if target is None or target["valid_until"] is not None:
                raise MissingSupersedeTarget(
                    f"record {record.id!r} supersedes {t.supersedes!r}, which is "
                    f"not a present current row in mneme; store the superseded "
                    f"record first.")

    def get(self, key: str) -> Record | None:
        _, rid = split_key(key)
        row = self._store.memory(rid)
        if row is None:
            return None
        return self._to_record(row, self._reverse_map())

    def records(self) -> list[Record]:
        rows = list(self._store.memories(include_superseded=True))
        new_to_old = _reverse_from(rows)
        return [self._to_record(r, new_to_old) for r in rows]

    def _reverse_map(self) -> dict:
        return _reverse_from(self._store.memories(include_superseded=True))

    def _to_record(self, row: Any, new_to_old: dict) -> Record:
        rid = row["id"]
        layer = row["layer"]
        kind = (KIND_SYNTHESIZED_PERSONA_L3 if layer == PERSONA_LAYER
                else KIND_EPISODIC_MEMORY)
        prov = Provenance(
            harness="mneme", source_hash=row["content_sha256"],
            native_id=f"mneme:{rid}", session_id=row["session"],
            create_ord=row["created_ord"])
        temporal = Temporal(valid_until=row["valid_until"],
                            supersedes=new_to_old.get(rid))
        data = {
            "layer": layer, "text": row["text"],
            "source_ids": json.loads(row["source_ids"]),
            "extractor": row["extractor"], "criterion": row["criterion"]}
        return Record(kind=kind, id=rid, scope=row["user"] or SCOPE_GLOBAL,
                      data=data, provenance=prov, temporal=temporal)


def _reverse_from(rows: Any) -> dict:
    """Map each record id to the id it supersedes. mneme stores the forward
    pointer (an old row's superseded_by names the newer row); canon's supersedes
    is the inverse, so a new row's supersedes is the old row that names it."""
    out: dict = {}
    for r in rows:
        newer = r["superseded_by"]
        if newer:
            out[newer] = r["id"]
    return out
