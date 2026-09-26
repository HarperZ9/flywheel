"""The keystore: item keys and the custody key, sealed by the OS (7.3).

Keys live in shards `state/keys/v1/owners/<owner>/<store>/<yyyy-mm>[-n].keys`,
one per store and UTC month, at most 4096 entries each. A shard is canonical
JSON sealed as a whole by the provider (DPAPI, or AES-GCM under a keychain
key). The custody key, used only for keyed references such as the import
exclusion list, sits in its own shard `custody.keys`.

A new key reaches disk before it is returned, so no ciphertext exists whose
key was never durable (I14): the shard is written to a temporary file,
flushed, renamed over the old one with write-through, and the directory is
flushed. Destroying a key rewrites its shard without it; older shard versions
left in freed clusters are still sealed, which is what bounds the claim in
design section 3.5. Rewrites run under the custody lock. Each instance caches
decrypted shards and reloads one when its file changes.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from .evidence_json import canonical_bytes
from .journey_lock import fsync_directory
from .trace_custody_lock import custody_lock
from .trace_enc import EncError, default_provider

MAX_SHARD_ENTRIES = 4096
SCHEMA = "flywheel.keystore-shard/v1"
CUSTODY = "custody.keys"
#: With no OS key store, shards are plain JSON behind this marker: the custody
#: key still works for keyed references, and status says nothing is encrypted.
PLAIN = b"FWKEYS-PLAIN\n"


def _replace(source: Path, target: Path) -> None:
    """Rename with write-through (MoveFileExW on Windows, rename elsewhere)."""
    if sys.platform != "win32":
        os.replace(source, target)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    kernel.MoveFileExW.restype = wintypes.BOOL
    if not kernel.MoveFileExW(str(source), str(target), 0x1 | 0x8):
        raise ctypes.WinError(ctypes.get_last_error())


class Keystore:
    def __init__(self, state_root, owner_ref: str, provider=None, *, clock=None) -> None:
        self.state_root = Path(state_root)
        self.owner_ref = owner_ref
        self.provider = provider or default_provider()
        self.dir = self.state_root / "keys" / "v1" / "owners" / owner_ref
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: dict[str, tuple[tuple, dict]] = {}

    def _context(self, path: Path) -> bytes:
        relative = path.relative_to(self.dir).as_posix()
        return f"flywheel.keystore.v1\0{self.owner_ref}\0{relative}".encode()

    def _read(self, path: Path) -> dict:
        try:
            info = path.stat()
        except FileNotFoundError:
            return {}
        stamp = (info.st_mtime_ns, info.st_size, getattr(info, "st_ino", 0))
        cached = self._cache.get(str(path))
        if cached and cached[0] == stamp:
            return cached[1]
        raw = path.read_bytes()
        if raw.startswith(PLAIN):
            body = raw[len(PLAIN):]
        elif self.provider.name == "none":
            raise EncError("OS_KEY_UNAVAILABLE")  # sealed by a key store no longer here
        else:
            body = self.provider.unseal(raw, self._context(path))
        doc = json.loads(body)
        if type(doc) is not dict or doc.get("schema") != SCHEMA:
            raise EncError("ENC_INTEGRITY")
        keys = {k: base64.b64decode(v) for k, v in doc["keys"].items()}
        self._cache[str(path)] = (stamp, keys)
        return keys

    def _write(self, path: Path, keys: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = canonical_bytes({"schema": SCHEMA, "keys": {
            k: base64.b64encode(v).decode("ascii") for k, v in sorted(keys.items())}})
        temporary = path.with_name(path.name + ".tmp")
        with open(temporary, "wb") as stream:
            stream.write(PLAIN + body if self.provider.name == "none"
                         else self.provider.seal(body, self._context(path)))
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, path)
        fsync_directory(path.parent)
        self._cache.pop(str(path), None)

    def shards(self, store: str) -> list[Path]:
        directory = self.dir / store
        return sorted(directory.glob("*.keys"), reverse=True) if directory.is_dir() else []

    def _find(self, store: str, item: str):
        for path in self.shards(store):
            keys = self._read(path)
            if item in keys:
                return path, keys
        return None, None

    def item_key(self, store: str, item: str, *, create: bool = False) -> bytes | None:
        path, keys = self._find(store, item)
        if path is not None or not create:
            return keys[item] if path is not None else None
        with custody_lock(self.state_root):
            path, keys = self._find(store, item)
            if path is not None:
                return keys[item]
            path = self._open_shard(store)
            keys = dict(self._read(path))
            keys[item] = os.urandom(32)
            self._write(path, keys)
            return keys[item]

    def _open_shard(self, store: str) -> Path:
        month = self.clock().strftime("%Y-%m")
        for suffix in range(0, 10_000):
            name = month + (f"-{suffix}" if suffix else "") + ".keys"
            path = self.dir / store / name
            if len(self._read(path)) < MAX_SHARD_ENTRIES:
                return path
        raise EncError("KEYSTORE_FULL")

    def destroy(self, store: str, items) -> int:
        """Rewrite every shard that holds any of `items` without them."""
        wanted, removed = set(items), 0
        with custody_lock(self.state_root):
            for path in self.shards(store):
                keys = self._read(path)
                hit = wanted & set(keys)
                if hit:
                    self._write(path, {k: v for k, v in keys.items() if k not in hit})
                    removed += len(hit)
        return removed

    def present(self, store: str, item: str) -> bool:
        return self._find(store, item)[0] is not None

    def custody_key(self, *, create: bool = True) -> bytes | None:
        path = self.dir / CUSTODY
        keys = self._read(path)
        if "custody" in keys or not create:
            return keys.get("custody")
        with custody_lock(self.state_root):
            keys = dict(self._read(path))
            if "custody" not in keys:
                keys["custody"] = os.urandom(32)
                self._write(path, keys)
            return keys["custody"]

    def unsealed_shards(self, store: str) -> list[bytes]:
        """The decrypted shard bytes, for verification that a key is gone."""
        out = []
        for path in self.shards(store):
            raw = path.read_bytes()
            out.append(raw[len(PLAIN):] if raw.startswith(PLAIN)
                       else self.provider.unseal(raw, self._context(path)))
        return out
