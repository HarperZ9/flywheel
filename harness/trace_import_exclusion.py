"""The import exclusion list: deleted sources do not come back (7.6, I19, SP-16).

One entry per deleted import keeps `HMAC(custody key, client, keyed path,
session id)`, the keyed path and keyed session on their own, the deleted
byte length `n`, and `HMAC(custody key, first n bytes)`. A source with the
same keyed identity is PREVIOUSLY_DELETED. A source at the same keyed path
or in the same keyed session whose first n bytes match a deleted prefix, as
a resumed session's transcript does, is PREVIOUSLY_DELETED_SESSION with the
count of new bytes, and nothing of the deleted prefix is stored. A prefix
never matches on its own: an empty or short deleted file would otherwise
match every later source that starts with the same bytes.

Deleting a captured session or any of its turns adds a session entry,
`HMAC(custody key, "session", client, session id)`, the same keyed ref the
turn store keeps. Every later source of that client and session is then
PREVIOUSLY_DELETED_SESSION, so a transcript that was captured but never
imported does not bring the deleted prompts back. This is the one keyed
fingerprint design invariant I5 allows: confirming a guess needs the owner's
custody key and the exact bytes. Without the custody key the list cannot
match, so imports fail closed with CUSTODY_KEY_UNAVAILABLE. Deleting an
import fills the list from the item's index row
(trace_delete_adapters_import); `add` writes an entry from source bytes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from .trace_custody_lock import custody_lock


class ExclusionUnavailable(Exception):
    code = "CUSTODY_KEY_UNAVAILABLE"


def list_path(home, owner_ref: str) -> Path:
    return Path(home) / "state" / "imports" / "v1" / "owners" / owner_ref / "exclusions.jsonl"


def custody_key(home, owner_ref: str) -> bytes:
    from .trace_enc import EncError
    from .trace_keystore import Keystore
    try:
        return Keystore(Path(home) / "state", owner_ref).custody_key()
    except (EncError, OSError, ValueError):
        raise ExclusionUnavailable() from None


def _mac(key: bytes, *parts) -> str:
    message = b"\x00".join(p if isinstance(p, bytes) else str(p).encode("utf-8") for p in parts)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def keyed_path(key: bytes, client: str, path) -> str:
    return _mac(key, "path", client, os.path.normcase(os.path.abspath(str(path))))


def source_ref(key: bytes, client: str, path, session_id) -> str:
    return _mac(key, "source", client, keyed_path(key, client, path), session_id or "none")


def prefix_ref(key: bytes, data: bytes) -> str:
    return _mac(key, "prefix", data)


def session_ref(key: bytes, client: str, session_id) -> str | None:
    """The keyed session ref the turn store uses; None without a session id."""
    from .trace_turn_receipt import keyed_ref
    return keyed_ref(key, "session", client, session_id) if session_id else None


def entries(home, owner_ref: str) -> list[dict]:
    path = list_path(home, owner_ref)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def add(home, owner_ref: str, client: str, path, session_id, data: bytes) -> dict:
    key = custody_key(home, owner_ref)
    entry = {"source": source_ref(key, client, path, session_id), "n": len(data),
             "prefix": prefix_ref(key, data), "path": keyed_path(key, client, path),
             "session": session_ref(key, client, session_id)}
    target = list_path(home, owner_ref)
    with custody_lock(Path(home) / "state"):
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "ab") as stream:
            stream.write(json.dumps(entry, sort_keys=True).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    return entry


class PrefixProbe:
    """Keyed digests of a stream's first n bytes for every n on the list."""

    def __init__(self, key: bytes, lengths) -> None:
        self.states = {n: hmac.new(key, b"prefix", hashlib.sha256) for n in set(lengths)
                       if n and n > 0}
        for state in self.states.values():
            state.update(b"\x00")
        self.seen = 0

    def feed(self, chunk: bytes) -> None:
        for n, state in self.states.items():
            if self.seen < n:
                state.update(chunk[:n - self.seen])
        self.seen += len(chunk)

    def digest(self, n: int) -> str | None:
        state = self.states.get(n)
        return state.hexdigest() if state is not None and self.seen >= n else None


def _bound(entry: dict, path_ref, session) -> bool:
    """A prefix match counts only for the same keyed path or keyed session."""
    return bool(path_ref and entry.get("path") == path_ref
                or session and entry.get("session") == session)


def check(key: bytes, listed: list[dict], source: str, size: int, probe: PrefixProbe, *,
          path_ref: str | None = None, session: str | None = None):
    """(state, new bytes) or (None, 0)."""
    for entry in listed:
        if entry.get("kind") == "session":
            if session and entry["session"] == session:
                return "PREVIOUSLY_DELETED_SESSION", size
            continue
        n = entry.get("n", 0)
        matches_prefix = n > 0 and probe.digest(n) == entry["prefix"]
        if entry["source"] == source or matches_prefix and _bound(entry, path_ref, session):
            if matches_prefix and size > n:
                return "PREVIOUSLY_DELETED_SESSION", size - n
            return "PREVIOUSLY_DELETED", 0
    return None, 0
