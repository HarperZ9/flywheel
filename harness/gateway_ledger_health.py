"""gateway_ledger_health.py -- a ledger that stops taking writes stops model calls.

The gateway opens its ledger at start (gateway_ledger). A ledger that opened
can still fail later: the disk fills, the folder goes away, a write is
refused. Before this module such a failure was seen only after the upstream
had answered, on every call, for as long as it lasted.

  write    puts one entry's line in the segment. When the write, or the
           commit to the disk, fails for any reason, the ledger is marked failed and the
           segment's file is closed, so nothing half written is sent later.
  usable   is asked by `gateway_ledger.for_home` before every model call. A
           failed ledger comes back as None, which every model interface
           answers with 503 before it contacts an upstream
           (gateway_ledger_gate). At most once a second it tries to resume,
           and once more when the ledger closes (`settle`), so a gateway that
           stops while failed still leaves the record when the disk allows it.
  resume   reads the segment back from the disk. When it verifies and still
           begins with the entries this process holds, the gateway appends to
           it again, and its first entry is a `ledger_gap` that says what
           failed, when, how many appends were refused, and which entries
           are on disk although their append reported a failure
           (`unconfirmed`: a reply recorded there was held back). When the file's
           tail is cut short or differs, the segment is left as it is and a
           new segment records the break, as at a start (gateway_ledger).
  commits  `ledger.commits` is [count, seconds, seconds for started entries]:
           how many entries were committed to the disk and how long the
           operating system took inside `os.fsync`. The overhead gate reads
           it to tell the gateway's own time from the disk's
           (tests/test_gateway_overhead_timing.py).
  strays   names the files in the ledger folder that look like segments and
           are not (`segment-backup.jsonl`, `segment-000001 - Copy.jsonl`).
           They are never read as part of the ledger.

What this cannot do. Every model interface writes its entry after the
upstream has answered, because the entry holds the hash of the reply. So
every call already in flight when the failure is first seen has reached its
provider: a plain reply is then held back and answered 500, and a stream's
text has already left. Calls that start after it are refused before the
upstream.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict

_LOG = logging.getLogger(__name__)
SEGMENT = re.compile(r"segment-[0-9]{6}\.jsonl\Z")     # ASCII digits only
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
            began = time.perf_counter()
            os.fsync(ledger._file.fileno())
            took, spent = time.perf_counter() - began, ledger.__dict__.setdefault(
                "commits", [0, 0.0, 0.0])
            spent[0], spent[1] = spent[0] + 1, spent[1] + took
            spent[2] += took if entry.kind == "endpoint_call_started" else 0.0
    except Exception as exc:            # noqa: BLE001 - whatever stopped the write, calls stop
        _fail(ledger, exc)
        raise


def head(ledger, entry=None) -> None:
    """Rewrite the head record. A failure marks the ledger failed, as a failed append does.

    `entry` is then already in the segment while its caller is told the append
    failed, so the resumed ledger names it as unconfirmed (`resume`)."""
    try:
        ledger._write_head()
    except Exception as exc:            # noqa: BLE001
        _fail(ledger, exc)
        if entry is not None:
            ledger.failed["unconfirmed"] = [entry.seq]
        raise


def _fail(ledger, exc) -> None:
    ledger.failed = {"error": f"{type(exc).__name__}: {exc}", "refused": 1,
                     "since": int(ledger.clock()), "retry_at": time.monotonic() + RETRY_SECONDS}
    try:
        ledger._file.close()            # nothing held in a buffer may reach the file later
    except Exception:                   # noqa: BLE001 - the file is given up either way
        _LOG.info("gateway ledger segment closed with its last write unfinished")
    _LOG.error("GATEWAY LEDGER WRITE FAILED (%s). Model calls answer 503 and reach no "
               "provider until the ledger can be written again. Calls already in flight "
               "had reached their provider.", ledger.failed["error"])


def usable(ledger):
    """`ledger` when it takes writes, else None. A failed ledger is tried again here."""
    failed = ledger.failed
    if failed is None:
        if ledger.calls.orphans:        # an operator may have left a request to settle one
            from .gateway_ledger_settle import sweep
            sweep(ledger)
        return ledger
    with ledger._lock:
        if ledger.failed is None:
            return ledger
        if time.monotonic() < failed["retry_at"]:
            return None
        failed["retry_at"] = time.monotonic() + RETRY_SECONDS
        try:
            resume(ledger)
        except Exception as exc:        # noqa: BLE001 - still failed, whatever the reason
            _LOG.error("gateway ledger still unavailable (%s: %s); model calls are refused",
                       type(exc).__name__, exc)
            return None
    return ledger


def settle(ledger) -> None:
    """Before a ledger closes: if its writes had failed, try once more to record the gap."""
    if ledger.failed is None:
        return
    try:
        resume(ledger)
    except Exception as exc:            # noqa: BLE001
        _LOG.error("gateway ledger closed while its writes still failed (%s: %s); %d append(s) "
                   "were refused and the ledger does not record them", type(exc).__name__, exc,
                   ledger.failed["refused"])


def resume(ledger) -> None:
    """Append to the ledger again after a failed write, and record the gap."""
    from . import gateway_ledger as base
    failed, where = ledger.failed, base.folder(ledger.home)
    kept = (ledger.path, ledger.entries, ledger._base)
    header, entries, start, problem = base.read_segment(ledger.path)
    held = [entry.entry_hash for entry in ledger.entries]
    same = problem is None and [e.entry_hash for e in entries[:len(held)]] == held
    # Entries on disk whose append reported a failure: the head record could not be
    # rewritten, or the line reached the disk although its write raised. The caller of
    # each was told the append failed, so a reply recorded there was held back.
    known = {entry.seq: entry for entry in (entries if same else ledger.entries)}
    late = entries[len(held):] if same else []
    seqs = set(failed.get("unconfirmed", ())) | {entry.seq for entry in late}
    shaky = [known[seq] for seq in sorted(seqs) if seq in known]
    unconfirmed = [{"segment": ledger.path.name, "seq": entry.seq, "kind": entry.kind,
                    "entry_hash": entry.entry_hash} for entry in shaky]
    try:
        if same:
            ledger.entries = entries    # a line that reached the disk although its write failed
        else:
            ledger._start(where, ledger.path.name,
                          entries[-1].entry_hash if entries else start,
                          f"a write failed ({failed['error']}) and left: "
                          f"{problem or 'entries this gateway did not write'}")
        ledger._file = ledger._held.enter_context(open(ledger.path, "ab", buffering=0))
        record = where / base.HEAD
        ledger._head = ledger._held.enter_context(
            open(record, "r+b" if record.exists() else "w+b"))
        ledger.failed = None
        ledger.append(GAP, "append_failed", {
            "reason": "append_failed", "error": failed["error"], "since": failed["since"],
            "until": int(ledger.clock()), "appends_refused": failed["refused"],
            **({"unconfirmed": unconfirmed} if unconfirmed else {})})
        ledger.calls.flush(ledger, shaky)   # the ends of the calls that were in flight
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
