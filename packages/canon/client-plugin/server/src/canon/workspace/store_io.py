"""store_io.py -- the file operations under the project store.

Reading a row file refuses it whole when any row names another project; writes
replace a file atomically; a log entry is appended with a sequence number; and
a run lock serializes writers. `store.py` builds the per-project rules on these.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from canon.concurrency import acquire_run_lock, release_run_lock
from canon.schema import Record
from canon.workspace.rows import ProjectRow, decode_rows

LOG_SCHEMA = "canon.project-log/v1"


class IsolationError(Exception):
    """A read would mix projects: a file holds a row bound to another project,
    or a caller asked for another project's records without declaring it."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_digest(record: Record) -> str:
    """The sha256 of a record's canonical JSON, the digest the log carries."""
    return sha256_text(record.to_json())


def read_bound(path: Path, expected: str | None, *, label: str) -> list[ProjectRow]:
    """Read a row file and refuse it whole if any row names another project."""
    if not path.is_file():
        return []
    rows = decode_rows(path.read_text(encoding="utf-8"), source=label)
    foreign = sorted({str(r.project_id) for r in rows if r.project_id != expected})
    if foreign:
        raise IsolationError(
            f"{label} holds rows bound to {foreign}, not {expected!r}; refusing "
            "the file rather than mixing projects")
    return rows


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def append_log(path: Path, action: str, record: Record, detail: dict,
                when: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    seq = sum(1 for line in existing.splitlines() if line.strip()) + 1
    entry = {"schema": LOG_SCHEMA, "seq": seq, "action": action,
             "record_key": f"{record.scope}/{record.id}", "record_kind": record.kind,
             "record_sha256": record_digest(record), "time": when, **detail}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")


@contextmanager
def run_lock(root: Path, name: str) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = acquire_run_lock(root, name)
    try:
        yield
    finally:
        release_run_lock(lock)
