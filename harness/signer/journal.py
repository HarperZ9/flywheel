"""journal.py -- the signer's own memory of what it has signed, per store.

This file is what makes a signature mean "in this order, once". The signer
signs seq N for a store only when N is one past the last seq it signed and the
caller's previous seal equals the seal it signed at N - 1. A caller that asks
for an old sequence number with different content is refused, so a record the
signer attested cannot be replaced through the signer, and a store cannot be
restarted at seq 1 under the same id.

The journal lives in the signer's home, which the agent cannot write when the
signer runs under a separate identity.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

JOURNAL_NAME = "journal.json"


class JournalConflict(RuntimeError):
    """The request would rewrite or skip history the signer already signed."""


def _replace(src: Path, dst: Path, tries: int = 50) -> None:
    """os.replace, retried on Windows. There a reader holding the journal open
    (the anchor job, for a few microseconds) makes the replace fail with a
    sharing violation; one retry after a short sleep clears it."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if sys.platform != "win32" or i == tries - 1:
                raise
            time.sleep(0.005)


class Journal:
    def __init__(self, home: Path) -> None:
        self.path = Path(home) / JOURNAL_NAME
        self._lock = threading.Lock()

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, self.path)

    def stores(self) -> list:
        """Every store this signer has signed for. Read-only; the anchor job
        (anchor_job.py) uses it to find heads to anchor."""
        with self._lock:
            return sorted(self._read())

    def head(self, store: str) -> dict:
        with self._lock:
            last = self._read().get(store, {})
            return {"seq": last.get("seq", 0), "seal": last.get("seal", ""),
                    "rewinds": list(last.get("rewinds", []))}

    def advance(self, store: str, seq: int, prev: str, seal: str) -> bool:
        """Record (seq, seal) for ``store``. Returns False for an exact retry
        of the last signed record, True for a new one. Raises on a conflict."""
        with self._lock:
            data = self._read()
            last = data.get(store, {"seq": 0, "seal": ""})
            if seq == last["seq"] and seal == last["seal"] and seq > 0:
                return False
            if seq <= last["seq"]:
                raise JournalConflict(
                    f"seq {seq} was already signed for this store (last signed "
                    f"{last['seq']}); signed history is not rewritten")
            if seq != last["seq"] + 1:
                raise JournalConflict(
                    f"seq {seq} skips ahead; the next seq for this store is "
                    f"{last['seq'] + 1}")
            if prev != last["seal"]:
                raise JournalConflict(
                    "prev does not equal the seal signed at the previous seq")
            data[store] = {"seq": seq, "seal": seal, "prev": prev,
                           "rewinds": last.get("rewinds", [])}
            self._write(data)
            return True

    def rewind(self, store: str, at: str) -> dict:
        """Forget the last signed record of ``store``, once, on the owner's
        say-so. For one case only: the signer signed seq N but the store never
        wrote it (the hook was killed between the two), so every later append
        conflicts and the hook fails closed. The rewind is kept in the journal
        and in every later signed head, so it is never silent."""
        with self._lock:
            data = self._read()
            last = data.get(store)
            if not last or last["seq"] < 1 or "prev" not in last:
                raise JournalConflict("nothing to rewind for this store")
            rewinds = last.get("rewinds", []) + [
                {"seq": last["seq"], "seal": last["seal"], "at": at}]
            data[store] = {"seq": last["seq"] - 1, "seal": last["prev"],
                           "rewinds": rewinds}
            self._write(data)
            return data[store]
