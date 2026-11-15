"""backends/flywheel.py -- FlywheelBackend: authored blocks and graph kinds.

flywheel's store holds canon's authored blocks and any kind that is not a
temporal memory. This adapter maps a Record onto an injected flywheel store
handle (no import of the flywheel package; a duck-typed handle with flywheel's
surface, proved against a fake that mirrors the source). The whole canonical
envelope is stored in flywheel's opaque `data` blob, keyed by (scope, id) as the
entity id and namespaced by `project=canon:<scope>` so canon's records stay
isolated in a store it may share.

Declared drop. flywheel's entities table has no temporal columns, so it holds
only current records: a record carrying live temporal history (`valid_until` or
`supersedes`) is refused by put(); a caller stores it current-only by calling
flatten() first, which strips the temporal block. Either way `temporal` is
declared dropped, and mneme remains the home for anything whose history matters.
"""
from __future__ import annotations

from typing import Any, Protocol

from canon.schema import KINDS, SCOPES, Record

from .base import CAP_TEMPORAL, flatten_for_drops, guard_put, record_key


class FlywheelStore(Protocol):
    """The slice of flywheel's store surface this adapter uses."""

    def put_entity(self, kind: str, data: dict, *, project: str = "",
                   eid: "str | None" = None) -> Any: ...

    def get_entity(self, eid: str) -> Any: ...

    def query_all_entities(self, *, kind: "str | None" = None,
                           project: "str | None" = None,
                           chunk: int = 500) -> Any: ...


class FlywheelBackend:
    name = "flywheel"

    def __init__(self, store: FlywheelStore) -> None:
        self._store = store

    def supported_kinds(self) -> frozenset[str]:
        return frozenset(KINDS)

    def declared_drops(self) -> frozenset[str]:
        return frozenset({CAP_TEMPORAL})

    def flatten(self, record: Record) -> Record:
        return flatten_for_drops(record, self.declared_drops())

    def _project(self, scope: str) -> str:
        return f"canon:{scope}"

    def put(self, record: Record) -> None:
        guard_put(self, record)
        self._store.put_entity(
            record.kind, record.to_dict(),
            project=self._project(record.scope), eid=record_key(record))

    def get(self, key: str) -> Record | None:
        ent = self._store.get_entity(key)
        if not ent:
            return None
        return Record.from_dict(ent["data"])

    def records(self) -> list[Record]:
        out: list[Record] = []
        for scope in SCOPES:
            light = self._store.query_all_entities(project=self._project(scope))
            for row in light:
                ent = self._store.get_entity(row["eid"])
                if ent:
                    out.append(Record.from_dict(ent["data"]))
        return out
