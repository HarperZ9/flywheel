"""The items retention can act on, read from custody (7.4).

Gateway traces (S1) by the first record of each operation folder, captured
turns (CT) by their record files, imported items (IM) by the encrypted
index. Refs come from file headers and encrypted records, never from names a
request supplied.
"""
from __future__ import annotations

from pathlib import Path


def _size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def _traces(state: Path, owner: str) -> list[dict]:
    from .trace_delete_adapters_enc import _first_record_ref
    base = state / "gateway-agent-traces" / "v1" / "owners" / owner
    out = []
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        first = folder / "00000000.json"
        ref = _first_record_ref(folder) if first.is_file() else None
        if ref:
            out.append({"store": "S1", "ref": ref, "stored_at": first.stat().st_mtime,
                        "bytes": _size(folder)})
    return out


def _turns(home: Path, owner: str) -> list[dict]:
    from .trace_turn_store import TurnStore
    store = TurnStore(home, owner)
    paths = sorted(store.base.glob("*/*/turn_*.enc")) if store.base.is_dir() else []
    return [{"store": "CT", "ref": p.stem, "stored_at": p.stat().st_mtime,
             "bytes": p.stat().st_size} for p in paths]


def _imports(home: Path, owner: str) -> list[dict]:
    from .trace_import_items import ImportStore
    store = ImportStore(home, owner)
    out = []
    for row in store.index():
        manifest = store.base / row["client"] / row["item_ref"] / "manifest.enc"
        if manifest.is_file():
            out.append({"store": "IM", "ref": row["item_ref"],
                        "stored_at": manifest.stat().st_mtime, "bytes": row["bytes"]})
    return out


def all_items(home: Path, owner: str) -> list[dict]:
    return _traces(home / "state", owner) + _turns(home, owner) + _imports(home, owner)
