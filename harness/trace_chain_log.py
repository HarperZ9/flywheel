"""A hash-chained JSONL log with a head anchor, shared by custody logs.

Each line is one canonical JSON entry whose `entry_sha256` covers the entry
and whose `prior_sha256` is the line before, so an edited or removed line
breaks the chain. A head file beside the log holds the count and the last
digest, so a log cut short is caught (the method mneme uses for its audit
log). Truncating both files consistently is not caught here; the witness
exists for that. A torn final line from a crash is dropped on the next
append, never on a read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256
from .journey_lock import ExclusiveJourneyLock, fsync_directory

GENESIS = "0" * 64


class ChainedLog:
    def __init__(self, directory, name: str, schema: str, head_schema: str, *,
                 anchor: str | None = None, lock_timeout_s: float = 5.0) -> None:
        self.dir = Path(directory)
        self.path = self.dir / f"{name}.jsonl"
        self.anchor = self.dir / (anchor or f"{name}-head.json")
        self.schema, self.head_schema = schema, head_schema
        self.lock_timeout_s = lock_timeout_s

    def _owner_only(self) -> None:
        from .operation_grants import _secure_owner_only
        _secure_owner_only(self.dir, directory=True)

    def append_body(self, body: dict, *, invalid: Exception) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._owner_only()
        with ExclusiveJourneyLock.acquire(self.dir / ".lock", self.lock_timeout_s):
            entries, report = self._load(repair=True)
            if not report["ok"]:
                raise invalid
            head = entries[-1]["entry_sha256"] if entries else GENESIS
            entry = {**body, "schema": self.schema, "seq": len(entries), "prior_sha256": head}
            entry["entry_sha256"] = canonical_sha256(entry)
            with self.path.open("ab") as stream:
                stream.write(canonical_bytes(entry) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._write_anchor(len(entries) + 1, entry["entry_sha256"])
            return entry

    def entries(self, *, invalid=None) -> list[dict]:
        entries, report = self._load(repair=False)
        if not report["ok"]:
            raise invalid if invalid is not None else ValueError(report["reason"])
        return entries

    def verify(self) -> dict:
        return self._load(repair=False)[1]

    def _write_anchor(self, count: int, head: str) -> None:
        temporary = self.anchor.with_name(self.anchor.name + ".tmp")
        temporary.write_bytes(canonical_bytes({"schema": self.head_schema, "count": count,
                                               "head_sha256": head}))
        os.replace(temporary, self.anchor)
        fsync_directory(self.dir)

    def _load(self, *, repair: bool) -> tuple[list[dict], dict]:
        raw = self.path.read_bytes() if self.path.exists() else b""
        if raw and not raw.endswith(b"\n"):
            if not repair:
                return [], bad("TORN_TAIL")
            raw = raw[:raw.rfind(b"\n") + 1]
            with self.path.open("r+b") as stream:
                stream.truncate(len(raw))
        entries, head = [], GENESIS
        for number, line in enumerate(raw.splitlines()):
            try:
                entry = json.loads(line)
                digest = entry.pop("entry_sha256")
            except (ValueError, TypeError, KeyError, AttributeError):
                return [], bad("ENTRY_UNREADABLE")
            if canonical_sha256(entry) != digest:
                return [], bad("ENTRY_DIGEST")
            if entry.get("prior_sha256") != head or entry.get("seq") != number:
                return [], bad("CHAIN_BROKEN")
            entry["entry_sha256"] = head = digest
            entries.append(entry)
        return entries, self._against_anchor(entries, head)

    def _against_anchor(self, entries: list[dict], head: str) -> dict:
        if not self.anchor.exists():
            return ok(0, GENESIS, 0) if not entries else bad("ANCHOR_MISSING")
        try:
            anchor = json.loads(self.anchor.read_bytes())
            count, anchored = anchor["count"], anchor["head_sha256"]
        except (ValueError, TypeError, KeyError):
            return bad("ANCHOR_UNREADABLE")
        if type(count) is not int or count > len(entries):
            return bad("TRUNCATED")
        if count and entries[count - 1]["entry_sha256"] != anchored:
            return bad("HEAD_MISMATCH")
        return ok(len(entries), head, len(entries) - count)


def ok(entries: int, head: str, behind: int) -> dict:
    return {"ok": True, "entries": entries, "head": head, "anchor_behind": behind}


def bad(reason: str) -> dict:
    return {"ok": False, "reason": reason}
