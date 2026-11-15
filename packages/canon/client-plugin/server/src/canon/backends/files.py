"""backends/files.py -- FilesBackend: one JSON file per record.

A plain-files store. Each record is written to `{root}/{scope}/{quote(id)}.json`
as its canonical to_dict(), and read back field-identical. It holds every kind
and loses no record field. What it does NOT have is flywheel's hash-chained
audit, so it declares `audit-chain` dropped: it will not pretend a directory of
files carries a verifiable chain. Git-or-nothing -- integrity for a files store
is the surrounding version control, kept as an honest null rather than a
home-grown half-chain that would read as more than it is.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from canon.schema import KINDS, Record

from .base import (
    CAP_AUDIT_CHAIN,
    flatten_for_drops,
    guard_put,
    record_key,
    split_key,
)


class FilesBackend:
    name = "files"

    def __init__(self, root: "str | Path") -> None:
        self._root = Path(root)

    def supported_kinds(self) -> frozenset[str]:
        return frozenset(KINDS)

    def declared_drops(self) -> frozenset[str]:
        return frozenset({CAP_AUDIT_CHAIN})

    def flatten(self, record: Record) -> Record:
        return flatten_for_drops(record, self.declared_drops())

    def _path(self, key: str) -> Path:
        scope, rid = split_key(key)
        return self._root / scope / (quote(rid, safe="") + ".json")

    def put(self, record: Record) -> None:
        guard_put(self, record)
        path = self._path(record_key(record))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.to_json(), encoding="utf-8")

    def get(self, key: str) -> Record | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return Record.from_json(path.read_text(encoding="utf-8"))

    def records(self) -> list[Record]:
        out: list[Record] = []
        if not self._root.is_dir():
            return out
        for scope_dir in sorted(self._root.iterdir()):
            if not scope_dir.is_dir():
                continue
            for f in sorted(scope_dir.glob("*.json")):
                out.append(Record.from_json(f.read_text(encoding="utf-8")))
        return out
