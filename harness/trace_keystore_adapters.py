"""Export and delete adapters for the keystore (store KS).

An export never carries a key: it lists how many shards each store has, so a
reader can see which stores are encrypted. Deleting the whole keystore makes
every encrypted item unreadable; it belongs only to a whole-custody deletion.
"""
from __future__ import annotations

from pathlib import Path


def _root(home) -> Path:
    return Path(home) / "state" / "keys" / "v1" / "owners"


def export_records(home) -> list[dict]:
    rows = []
    root = _root(home)
    for owner in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        for store in sorted(p for p in owner.iterdir() if p.is_dir()):
            rows.append({"owner_ref": owner.name, "store": store.name,
                         "shards": len(list(store.glob("*.keys")))})
        rows.extend({"owner_ref": owner.name, "store": f.stem, "floor": True}
                    for f in sorted(owner.glob("*.floor")))
    return rows


def delete_all(home) -> dict:
    root = Path(home) / "state" / "keys"
    removed = 0
    for path in sorted(root.rglob("*"), reverse=True) if root.exists() else []:
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1
        elif path.is_dir():
            path.rmdir()
    return {"removed": removed}
