"""The owner-level custody lock, `state/custody.lock` (7.3, 7.10, SP-15).

One lock file serializes keystore rewrites with deletion, capture, import and
export, so a key is never destroyed while another writer is about to use it.
It is a dedicated lock file, never the ledger itself, so a write to the
ledger cannot collide with a byte-range lock (flywheel #292). The lock is
reentrant within a thread: a deletion that holds it can rewrite the keystore
without waiting on itself.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import threading

from .journey_lock import ExclusiveJourneyLock

FILENAME = "custody.lock"
_HELD = threading.local()


def lock_path(state_root) -> Path:
    return Path(state_root) / FILENAME


@contextmanager
def custody_lock(state_root, timeout_s: float = 10.0):
    key = os.path.normcase(os.path.abspath(str(lock_path(state_root))))
    held = getattr(_HELD, "depth", None)
    if held is None:
        held = _HELD.depth = {}
    if held.get(key):
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    with ExclusiveJourneyLock.acquire(Path(key), timeout_s):
        held[key] = 1
        try:
            yield
        finally:
            held[key] = 0


def is_held(state_root) -> bool:
    key = os.path.normcase(os.path.abspath(str(lock_path(state_root))))
    return bool(getattr(_HELD, "depth", {}).get(key))
