"""gateway_ledger_health.py -- a ledger that stops taking writes stops model calls.

The gateway opens its ledger at start (gateway_ledger). A ledger that opened
can still fail later: the disk fills, the folder goes away, a write is
refused. Before this module such a failure was seen only after the upstream
had answered, on every call, for as long as it lasted.

  write    puts one entry's line in the segment. When the write, or the
           commit to the disk, fails, the ledger is marked failed and the
           segment's file is closed, so nothing half written is sent later.
  usable   is asked by `gateway_ledger.for_home` before every model call. A
           failed ledger comes back as None, which every model interface
           answers with 503 before it contacts an upstream
           (gateway_ledger_gate). At most once a second it tries to resume.
  resume   reads the segment back from the disk. When it verifies and still
           begins with the entries this process holds, the gateway appends to
           it again, and its first entry is a `ledger_gap` that says what
           failed, when, and how many appends were refused. When the file's
           tail is cut short or differs, the segment is left as it is and a
           new segment records the break, as at a start (gateway_ledger).
  strays   names the files in the ledger folder that look like segments and
           are not (`segment-backup.jsonl`, `segment-000001 - Copy.jsonl`).
           They are never read as part of the ledger.

What this cannot do. Every model interface writes its entry after the
upstream has answered, because the entry holds the hash of the reply. So the
one call during which the failure is first seen has already reached the
provider: a plain reply is then held back and answered 500, and a stream's
text has already left. Calls after it are refused before the upstream.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict

_LOG = logging.getLogger(__name__)
SEGMENT = re.compile(r"segment-\d{6}\.jsonl\Z")
RETRY_SECONDS = 1.0                     # between attempts to resume a failed ledger
GAP = "ledger_gap"                      # the entry a resumed ledger starts with


class LedgerDown(OSError):
    """The ledger stopped taking writes and has not resumed."""


def strays(where) -> list:
    """Names in the ledger folder that match `segment-*` and are not segments."""
    try:
        return sorted(path.name for path in where.glob("segment-*")
                      if not SEGMENT.match(path.name))
    except OSError:
        return []


def _put(file, data: bytes) -> None:
    """Write all of `data`. An unbuffered file may take part of it and say so."""
    view = memoryview(data)
    while view:
        done = file.write(view)
        if not done:
            raise OSError("the ledger segment took no bytes")
        view = view[done:]
    file.flush()


def write(ledger, entry) -> None:
    """Put `entry` in the segment and commit it, or mark the ledger failed and raise."""
    if ledger.failed is not None:
        ledger.failed["refused"] += 1
        raise LedgerDown(ledger.failed["error"])
    line = json.dumps(asdict(entry), ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        _put(ledger._file, line)
        if ledger._sync:
            os.fsync(ledger._file.fileno())
    except (OSError, ValueError) as exc:
        _fail(ledger, exc)
        raise


def _fail(ledger, exc) -> None:
    ledger.failed = {"error": f"{type(exc).__name__}: {exc}", "refused": 1,
                     "since": int(ledger.clock()), "retry_at": time.monotonic() + RETRY_SECONDS}
    try:
        ledger._file.close()            # nothing held in a buffer may reach the file later
    except (OSError, ValueError):
        _LOG.info("gateway ledger segment closed with its last write unfinished")
    _LOG.error("GATEWAY LEDGER WRITE FAILED (%s). Model calls answer 503 and reach no "
               "provider until the ledger can be written again. The call that met the "
               "failure had already reached its provider.", ledger.failed["error"])


def usable(ledger):
    """`ledger` when it takes writes, else None. A failed ledger is tried again here."""
    failed = ledger.failed
    if failed is None:
        return ledger
    with ledger._lock:
        if ledger.failed is None:
            return ledger
        if time.monotonic() < failed["retry_at"]:
            return None
        failed["retry_at"] = time.monotonic() + RETRY_SECONDS
        try:
            resume(ledger)
        except (OSError, ValueError) as exc:
            _LOG.error("gateway ledger still unavailable (%s: %s); model calls are refused",
                       type(exc).__name__, exc)
            return None
    return ledger


def resume(ledger) -> None:
    """Append to the ledger again after a failed write, and record the gap."""
    from . import gateway_ledger as base
    failed, where = ledger.failed, base.folder(ledger.home)
    kept = (ledger.path, ledger.entries, ledger._base)
    header, entries, start, problem = base.read_segment(ledger.path)
    held = [entry.entry_hash for entry in ledger.entries]
    same = problem is None and [e.entry_hash for e in entries[:len(held)]] == held
    try:
        if same:
            ledger.entries = entries    # a line that reached the disk although its write failed
        else:
            ledger._start(where, ledger.path.name,
                          entries[-1].entry_hash if entries else start,
                          f"a write failed ({failed['error']}) and left: "
                          f"{problem or 'entries this gateway did not write'}")
        ledger._file = ledger._held.enter_context(open(ledger.path, "ab", buffering=0))
        ledger.failed = None
        ledger.append(GAP, "append_failed", {
            "reason": "append_failed", "error": failed["error"], "since": failed["since"],
            "until": int(ledger.clock()), "appends_refused": failed["refused"]})
    except BaseException:
        if ledger.path != kept[0]:      # a new segment that could not be started
            try:
                os.unlink(ledger.path)
            except OSError:
                _LOG.error("gateway ledger: %s was left behind unfinished", ledger.path.name)
        ledger.path, ledger.entries, ledger._base = kept
        ledger.failed = failed          # still failed, with the first cause and the count
        raise
    _LOG.error("gateway ledger writes resumed after %s; %d append(s) were refused in between "
               "and the ledger records the gap", failed["error"], failed["refused"])
