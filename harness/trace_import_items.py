"""Imported items in encrypted custody (7.6, store IM).

One item per source file under
`state/imports/v1/owners/<owner>/<client>/<item_ref>/`: the exact source bytes
in 8 MiB encrypted chunks, an encrypted manifest (keyed source identity,
sizes, identities and digests before and after, catalog and parser versions,
line counts, the version it supersedes) and an encrypted redaction index. A
new item is staged in a dot-named folder and renamed into place only after
its source proved unchanged, so nothing is ever half imported. The index of
items is itself encrypted: it holds refs, client, kind, sizes and keyed
references only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets

from .evidence_json import canonical_bytes
from .trace_custody_lock import custody_lock
from .trace_enc_write import ItemCipher
from .trace_keystore import Keystore

STORE = "IM"
_REF = re.compile(r"imp_[0-9a-f]{32}\Z")
CHUNK = 8 * 1024 * 1024


class ImportStore:
    def __init__(self, home, owner_ref: str, provider=None) -> None:
        self.home, self.owner_ref = Path(home), owner_ref
        self.state = self.home / "state"
        self.base = self.state / "imports" / "v1" / "owners" / owner_ref
        self.provider = provider
        self.keystore = Keystore(self.state, owner_ref, provider)

    def cipher(self, item: str) -> ItemCipher:
        return ItemCipher(self.state, self.owner_ref, STORE, item, provider=self.provider,
                          keystore=self.keystore)

    def _read_json(self, path: Path, item: str, name: str):
        cipher = self.cipher(item)
        return json.loads(cipher.open(name, path.read_bytes()))

    def index(self) -> list[dict]:
        path = self.base / "index.enc"
        return self._read_json(path, "index", "index") if path.exists() else []

    def _write_index(self, rows: list[dict]) -> None:
        from . import trace_durable
        trace_durable.write_durable(self.base / "index.enc",
                                    self.cipher("index").seal("index", canonical_bytes(rows)))

    def item_refs(self) -> list[str]:
        return [row["item_ref"] for row in self.index()]

    def _dir(self, ref: str) -> Path:
        row = next(r for r in self.index() if r["item_ref"] == ref)
        return self.base / row["client"] / ref

    def manifest(self, ref: str) -> dict:
        return self._read_json(self._dir(ref) / "manifest.enc", ref, "manifest")

    def redaction_index(self, ref: str) -> list:
        return self._read_json(self._dir(ref) / "redaction.enc", ref, "redaction")

    def read_bytes(self, ref: str) -> bytes:
        directory, cipher = self._dir(ref), self.cipher(ref)
        out = b""
        for path in sorted(directory.glob("chunk-*.enc")):
            cipher.prefix.reset()
            out += cipher.open(path.stem, path.read_bytes())
        return out

    def stage(self, client: str) -> "StagedItem":
        return StagedItem(self, client)


class StagedItem:
    def __init__(self, store: ImportStore, client: str) -> None:
        self.store, self.client = store, client
        self.ref = "imp_" + secrets.token_hex(16)
        self.dir = store.base / f".staging-{self.ref}"
        self.dir.mkdir(parents=True)
        self.cipher = store.cipher(self.ref)
        self.buffer, self.count = b"", 0

    def _flush(self, data: bytes) -> None:
        name = f"chunk-{self.count:05d}"
        (self.dir / f"{name}.enc").write_bytes(self.cipher.seal(name, data))
        self.count += 1

    def write(self, chunk: bytes) -> None:
        self.buffer += chunk
        while len(self.buffer) >= CHUNK:
            self._flush(self.buffer[:CHUNK])
            self.buffer = self.buffer[CHUNK:]

    def finalize(self, manifest: dict, redaction: list, row: dict) -> str:
        if self.buffer or not self.count:
            self._flush(self.buffer)
            self.buffer = b""
        for name, doc in (("manifest", {**manifest, "item_ref": self.ref, "chunks": self.count}),
                          ("redaction", redaction)):
            (self.dir / f"{name}.enc").write_bytes(self.cipher.seal(name, canonical_bytes(doc)))
        final = self.store.base / self.client / self.ref
        with custody_lock(self.store.state):
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self.dir, final)
            rows = self.store.index()
            rows.append({**row, "item_ref": self.ref, "client": self.client})
            self.store._write_index(rows)
        return self.ref

    def discard(self) -> None:
        """Destroy the key, then remove the staging folder (and the final
        folder, when a failure came after the rename but before the index)."""
        from .trace_meta_adapters import remove_tree
        self.store.keystore.destroy(STORE, [self.ref])
        for folder in (self.dir, self.store.base / self.client / self.ref):
            remove_tree(folder)


def sweep_staging(home, *, min_age_s: float = 3600.0, now: float | None = None) -> int:
    """Gateway start: staging folders a crash left behind hold decryptable
    chunks that no index row, plan or deletion reaches. Each one untouched for
    `min_age_s` (an import still running keeps writing) loses its key, then
    its folder. Returns the folders removed."""
    import time
    from .trace_meta_adapters import remove_tree
    now, removed = time.time() if now is None else now, 0
    for owner in _owners(home):
        store = ImportStore(home, owner)
        for folder in sorted(store.base.glob(".staging-imp_*")):
            ref = folder.name[len(".staging-"):]
            if not _REF.fullmatch(ref) or now - _newest(folder) < min_age_s:
                continue
            store.keystore.destroy(STORE, [ref])
            remove_tree(folder)
            removed += 1
    return removed


def _newest(folder: Path) -> float:
    stamps = [folder.lstat().st_mtime]
    stamps += [p.lstat().st_mtime for p in folder.iterdir()]
    return max(stamps)


def _owners(home) -> list[str]:
    base = Path(home) / "state" / "imports" / "v1" / "owners"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def export_records(home) -> list[dict]:
    """Export adapter: each imported item's manifest; bytes are read per item."""
    out = []
    for owner in _owners(home):
        store = ImportStore(home, owner)
        out.extend({"owner_ref": owner, **store.manifest(ref)} for ref in store.item_refs())
    return out


def delete_all(home) -> dict:
    """Delete adapter for a whole-custody deletion: keys first, then files."""
    from .trace_meta_adapters import remove_tree
    removed = 0
    for owner in _owners(home):
        store = ImportStore(home, owner)
        store.keystore.destroy(STORE, store.item_refs() + ["index"])
        removed += remove_tree(store.base)
    return {"removed": removed}
