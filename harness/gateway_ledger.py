"""gateway_ledger.py -- the gateway's ledger, kept on disk.

The gateway records every routed call in one hash-chained ledger. Until 2.0
that ledger lived in process memory and was lost when the gateway stopped.
This module keeps it under the Flywheel home, in the JSONL entry format the
coding session saves (`harness.local_session`):

  <home>/gateway-ledger/segment-000001.jsonl   a header line, then one entry per line
  <home>/gateway-ledger/head                   where the chain ends, rewritten in place
  <home>/gateway-ledger/writer.lock            held by the one gateway that appends

Append. Each entry is written to the segment and committed to the disk
(fsync) before `append` returns; the head record is then rewritten. The
gateway appends before it sends a plain reply and before the last event of a
stream, so the entry is on disk first. The text of a stream leaves before
its entry exists, because the entry hashes the whole reply.
`FLYWHEEL_GATEWAY_LEDGER_SYNC=0` skips the fsync: a process crash still
loses nothing, and a power loss can lose the entries the operating system
had not yet written.

Chain. The first entry of a segment links to the SHA-256 of the segment's
header line, so the header is inside the chain. A new process loads the last
segment, checks every hash and link and the head record, and goes on from
the last entry.

Break. A segment that does not verify is never appended to. The gateway logs
the break at error level and starts a new segment whose header names the
broken one, the last hash that still verified and what was wrong. `verify`
then reports the broken segment and fails.

Limit. The head record makes a shortened file detectable. A process of the
same user that rewrites the segment and the head together is not detected by
this file alone; `flywheel anchor` has outside parties witness a head.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import ExitStack
from pathlib import Path

from . import gateway_ledger_health as _health
from .gateway_calls import Calls
from .local_session import Entry, SessionLedger

_LOG = logging.getLogger(__name__)
SCHEMA = "flywheel.gateway-ledger/v1"
DIR, HEAD, LOCK = "gateway-ledger", "head", "writer.lock"
SYNC_ENV = "FLYWHEEL_GATEWAY_LEDGER_SYNC"
ROTATE_AT = 50_000                      # entries; a full segment is closed at the next start
_HEAD_WIDTH = 200
_FIELDS = ("seq", "kind", "content", "meta", "prev_hash", "entry_hash")
GONE = "the head record is there and no segment file is: the segments were removed"


class LedgerBusy(Exception):
    """Another gateway process is appending to this home's ledger."""


def folder(home) -> Path:
    return Path(home) / DIR


def segments(home) -> list:
    """The segment files of a home, oldest first. A file whose name is not exactly
    a segment's (a copy, a backup) is not one (gateway_ledger_health.strays)."""
    where = folder(home)
    return sorted(p for p in where.glob("segment-*.jsonl")
                  if _health.SEGMENT.match(p.name)) if where.is_dir() else []


def _sha(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def read_segment(path) -> tuple:
    """(header, entries, base, problem). `entries` are the ones that verify, in
    order; `problem` says what is wrong after them, or is None."""
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [], "", f"cannot be read ({type(exc).__name__})"
    lines = text.split("\n")
    cut = lines[-1] != ""               # no newline after the last line: it was cut short
    lines = lines if cut else lines[:-1]
    try:
        header = json.loads(lines[0]) if lines else None
    except ValueError:
        header = None
    if not isinstance(header, dict) or header.get("schema") != SCHEMA:
        return None, [], "", "line 1 is not a gateway ledger header"
    base = prev = _sha(lines[0])
    entries = []
    for number, line in enumerate(lines[1:], start=2):
        last = cut and number == len(lines)
        try:
            row = json.loads(line)
            entry = Entry(**{name: row[name] for name in _FIELDS})
            good = (len(row) == len(_FIELDS) and entry.seq == len(entries)
                    and entry.prev_hash == prev and isinstance(entry.meta, dict)
                    and Entry.compute_hash(entry.seq, entry.kind, entry.content, entry.meta,
                                           entry.prev_hash) == entry.entry_hash)
        except (ValueError, KeyError, TypeError):
            good = False
        if not good or last:
            return header, entries, base, (f"line {number} is cut short" if last
                                           else f"line {number} does not verify")
        entries.append(entry)
        prev = entry.entry_hash
    return header, entries, base, None


def read_head(home) -> "dict | None":
    try:
        found = json.loads((folder(home) / HEAD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _against_head(home, path, header, entries, head=...) -> "str | None":
    """What the head record says is wrong with the last segment, or None. `head` is
    the record as read before the segment, so an append in between is not a fault."""
    head = read_head(home) if head is ... else head
    if head is None:
        return "the head record is missing or unreadable"
    if head.get("segment") != Path(path).name:
        if header.get("previous") == head.get("segment") and not entries:
            return None                 # stopped between a new segment and its head record
        return "the head record names another segment"
    count = head.get("entries")
    if not isinstance(count, int) or count > len(entries):
        return (f"the file holds {len(entries)} entries and the head record {count}: "
                "entries were removed")
    if count and entries[count - 1].entry_hash != head.get("head"):
        return f"entry {count - 1} is not the one the head record names"
    return None


def check(home) -> list:
    """Every segment, oldest first: {name, entries, head, ok, problem, header, rows}."""
    head = read_head(home) or read_head(home)   # before the segments: a gateway may append
    out, paths = [], segments(home)
    if not paths and (folder(home) / HEAD).exists():
        return [{"name": "(no segment)", "entries": 0, "ok": False, "head": "", "rows": [],
                 "header": {}, "problem": GONE}]
    for index, path in enumerate(paths):
        header, entries, base, problem = read_segment(path)
        if problem is None and index == len(paths) - 1:
            problem = _against_head(home, path, header, entries, head)
        if problem is None and header.get("previous") != (
                out[-1]["name"] if out else None):
            problem = "the header does not name the segment before it"
        if problem is None and out and header.get("previous_state") == "verified" and (
                not out[-1]["ok"] or header.get("previous_head") != out[-1]["head"]):
            problem = "the header's link to the segment before it does not hold"
        out.append({"name": path.name, "entries": len(entries), "ok": problem is None,
                    "head": entries[-1].entry_hash if entries else base,
                    "problem": problem, "header": header or {}, "rows": entries})
    return out


class GatewayLedger(SessionLedger):
    """A `SessionLedger` whose entries are on disk before `append` returns."""

    def __init__(self, home, clock=time.time):
        super().__init__()
        self.home, self.clock, self.found_broken = Path(home), clock, None
        self.failed = None              # set while writes fail (gateway_ledger_health)
        self._lock, self._held = threading.RLock(), ExitStack()
        self._sync = os.environ.get(SYNC_ENV, "").strip().lower() not in ("0", "false", "no")
        where = folder(home)
        where.mkdir(parents=True, exist_ok=True)
        from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
        try:
            self._held.enter_context(ExclusiveJourneyLock.acquire(where / LOCK, 0.0))
        except JourneyLockBusy as exc:
            raise LedgerBusy("another gateway process is appending to the ledger of this "
                             "Flywheel home") from exc
        try:
            self._open(where)
        except BaseException:
            self._held.close()
            raise

    def _open(self, where: Path) -> None:
        paths = segments(self.home)
        header, entries, base = None, [], ""
        problem = GONE if not paths and (where / HEAD).exists() else None
        if paths:
            header, entries, base, problem = read_segment(paths[-1])
            if problem is None:
                problem = _against_head(self.home, paths[-1], header, entries)
        self.calls = Calls(header, entries)     # started and never ended: unsettled now
        if paths and problem is None and len(entries) < ROTATE_AT:
            self.path, self.entries, self._base = paths[-1], entries, base
        else:
            if problem is not None:
                self.found_broken = f"{paths[-1].name if paths else HEAD}: {problem}"
                _LOG.error("GATEWAY LEDGER BROKEN: %s. It is left as it is and not appended "
                           "to; a new segment records the break. Run `flywheel "
                           "gateway-ledger verify`.", self.found_broken)
            self._start(where, paths[-1].name if paths else None,
                        (entries[-1].entry_hash if entries else base) if paths else None,
                        problem)
        self._file = self._held.enter_context(open(self.path, "ab", buffering=0))
        self._head = self._held.enter_context(open(where / HEAD, "r+b" if (
            where / HEAD).exists() else "w+b"))
        self._write_head()
        self.calls.announce(self)

    def _start(self, where: Path, previous, previous_head, problem) -> None:
        number = int(previous[8:14]) + 1 if previous else 1
        state = "broken" if problem else ("none" if previous is None else "verified")
        header = json.dumps({
            "schema": SCHEMA, "segment": number, "previous": previous,
            "previous_head": previous_head, "previous_state": state,
            "reason": problem or ("first segment" if previous is None else "rotation"),
            "started": int(self.clock()), **self.calls.carried()}, sort_keys=True)
        self.path = where / f"segment-{number:06d}.jsonl"
        with open(self.path, "xb") as made:
            made.write(header.encode("utf-8") + b"\n")
            made.flush()
            os.fsync(made.fileno())
        self.entries, self._base = [], _sha(header)

    def _write_head(self) -> None:
        record = json.dumps({"segment": self.path.name, "entries": len(self.entries),
                             "head": self.checkpoint()})
        self._head.seek(0)
        self._head.write(record.ljust(_HEAD_WIDTH).encode("utf-8") + b"\n")
        self._head.flush()              # not fsynced: a head behind the segment is accepted

    def append(self, kind: str, content: str, meta: "dict | None" = None) -> Entry:
        """Chain one entry and put it in the file. Raises OSError when it cannot;
        the ledger then refuses appends until it resumes (gateway_ledger_health)."""
        meta = meta or {}
        with self._lock:
            seq = len(self.entries)
            prev = self.entries[-1].entry_hash if self.entries else self._base
            entry = Entry(seq, kind, content, meta, prev,
                          Entry.compute_hash(seq, kind, content, meta, prev))
            _health.write(self, entry)
            self.entries.append(entry)
            self.calls.note(entry)
            _health.head(self, entry)
            return entry

    def verify(self) -> bool:
        prev = self._base
        for index, entry in enumerate(self.entries):
            if entry.seq != index or entry.prev_hash != prev or Entry.compute_hash(
                    entry.seq, entry.kind, entry.content, entry.meta,
                    entry.prev_hash) != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def checkpoint(self) -> str:
        return self.entries[-1].entry_hash if self.entries else self._base

    def close(self) -> None:
        with self._lock:
            _health.settle(self)        # a ledger that failed gets one more try to record it
            self._held.close()


_OPEN, _OPEN_LOCK = {}, threading.Lock()    # at most one home's ledger is open


def for_home(home) -> "GatewayLedger | None":
    """The open ledger of a home, opened on first use. None, with the reason
    logged at error level, when it cannot be opened; a call is then refused
    rather than served without a record."""
    key = os.path.normcase(os.path.abspath(str(home)))
    with _OPEN_LOCK:
        if key not in _OPEN:
            for other in list(_OPEN):
                _OPEN.pop(other).close()
            try:
                _OPEN[key] = GatewayLedger(home)
            except (LedgerBusy, OSError) as exc:
                _LOG.error("gateway ledger unavailable (%s: %s); model calls are refused "
                           "until it can be written", type(exc).__name__, exc)
                return None
        return _health.usable(_OPEN[key])   # None while its writes fail


def close_all() -> None:
    with _OPEN_LOCK:
        for key in list(_OPEN):
            _OPEN.pop(key).close()


atexit.register(close_all)             # release the writer lock before shutdown
