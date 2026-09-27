"""Adopted settings are checked against the custody ledger (7.15, I17).

The presence method, the capture settings and the retention policy each live
in a small file the gateway reads. Presence gates the CLI commands and the
routes that change those files; it does not stop a process running as the
owner from writing a file directly. So a file counts as adopted only when
its digest equals the digest of the latest `settings_adopted` entry for that
setting in the verified custody ledger. A file that does not match reads as
SETTINGS_TAMPERED: the caller falls back to its defaults and status and the
prompt hook say so.

This raises the bar and leaves a trace; it does not make the files
unforgeable. Code that runs as the owner can also append a ledger entry,
and the witness event it would then lack is how that shows up.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading

TAMPERED = "SETTINGS_TAMPERED"
_CACHE: dict = {}
_LOCK = threading.Lock()


def _ledger_file(home, owner: str) -> Path:
    return (Path(home) / "state" / "custody-ledger" / "v1" / "owners" / owner
            / "ledger.jsonl")


def _stamp(path: Path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_size, info.st_mtime_ns


def latest(home, owner: str) -> dict:
    """{settings name: digest} from the latest adoption of each; raises
    LedgerError when the ledger does not verify."""
    from .trace_custody_ledger import CustodyLedger
    key = (str(Path(home)), owner)
    stamp = _stamp(_ledger_file(home, owner))
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == stamp and stamp is not None:
            return dict(cached[1])
    found: dict[str, str] = {}
    for entry in CustodyLedger(home, owner).entries():
        if entry["kind"] == "settings_adopted":
            found[entry["fields"].get("settings")] = entry["fields"].get("digest")
    with _LOCK:
        _CACHE[key] = (stamp, dict(found))
    return found


def adopted_digest(home, owner: str, settings: str) -> str | None:
    """The digest the ledger says was adopted last, or None; raises
    LedgerError when the ledger does not verify."""
    return latest(home, owner).get(settings)


def matches(home, owner: str, settings: str, digest: str) -> bool:
    """Whether `digest` is the adopted one. An unverifiable ledger never matches."""
    from .trace_custody_ledger import LedgerError
    try:
        return adopted_digest(home, owner, settings) == digest
    except (LedgerError, OSError, ValueError):
        return False
