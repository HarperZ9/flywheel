"""Counts, bytes and date ranges per registered store, and what nobody named.

Read-only: listing and `stat` only, no file is opened for content and nothing
is created, so `flywheel traces status` changes no store. Reparse points
(symbolic links, junctions) are counted as entries and never followed, so a
link planted in a store cannot pull another tree into the count.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from . import trace_inventory as inv

MAX_ENTRIES = 1_000_000
_REPARSE = 0x400


def resolve_roots(environ=None) -> dict:
    from .run_paths import run_root_default
    env = os.environ if environ is None else environ
    home = Path(env.get("FLYWHEEL_HOME") or Path.home() / ".flywheel")
    run = Path(env.get("FLYWHEEL_RUN_ROOT") or run_root_default())
    return {"home": home, "state": home / "state", "run": run, "lanes": home / "lanes",
            "temp": Path(tempfile.gettempdir()), "env": env}


def _is_link(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & _REPARSE)
    except OSError:
        return True


def _walk(path: Path, acc: dict) -> None:
    try:
        entries = list(os.scandir(path))
    except OSError:
        return
    for entry in entries:
        if acc["files"] + acc["dirs"] >= MAX_ENTRIES:
            acc["complete"] = False
            return
        if not _is_link(entry) and entry.is_dir(follow_symlinks=False):
            acc["dirs"] += 1
            _walk(Path(entry.path), acc)
        else:
            _count(Path(entry.path), acc)


def _count(path: Path, acc: dict) -> None:
    try:
        info = path.lstat()
    except OSError:
        return
    acc["files"] += 1
    acc["bytes"] += info.st_size
    acc["times"].append(info.st_mtime)


def file_inventory(paths) -> dict:
    """Files, bytes and modification range under `paths`, following no link."""
    acc = {"files": 0, "dirs": 0, "bytes": 0, "times": [], "complete": True}
    present = False
    for path in paths:
        path = Path(path)
        if not os.path.lexists(path):
            continue
        present = True
        if path.is_dir() and not path.is_symlink() and not _reparse(path):
            _walk(path, acc)
        else:
            _count(path, acc)
    times = acc["times"]
    return {"present": present, "files": acc["files"], "bytes": acc["bytes"],
            "first": _iso(min(times)) if times else None,
            "last": _iso(max(times)) if times else None, "complete": acc["complete"]}


def _reparse(path: Path) -> bool:
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & _REPARSE)
    except OSError:
        return True


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _names(directory: Path) -> list[str]:
    try:
        return sorted(entry.name for entry in os.scandir(directory))
    except OSError:
        return []


def store_paths(store: inv.Store, roots: dict) -> list[Path]:
    """Every path that holds this store's items under the resolved roots."""
    if store.root == "env":
        found = {roots["env"].get(k) for k in store.env} - {None, ""}
        return [Path(p) for p in sorted(found)]
    if store.root == "client":
        name = {"CLAUDE_CONFIG_DIR": ".claude", "CODEX_HOME": ".codex"}[store.env[0]]
        base = Path(roots["env"].get(store.env[0]) or Path.home() / name)
        return sorted({p for pattern in store.patterns for p in base.glob(pattern)
                       if p.is_file()})
    directory = roots[store.root]
    import fnmatch
    return [directory / n for n in _names(directory)
            if any(fnmatch.fnmatchcase(n, p) for p in store.patterns)]


def location_text(store: inv.Store) -> str:
    joined = ", ".join(store.patterns)
    if store.root == "state":
        return ", ".join(f"state/{p}" for p in store.patterns)
    if store.root == "lanes":
        return ", ".join(f"lanes/{p}" for p in store.patterns)
    if store.root == "run":
        return ", ".join(f"<run-root>/{p}" for p in store.patterns)
    if store.root == "env":
        return " or ".join(f"${k}" for k in store.env)
    if store.root == "temp":
        return f"<temp>/{joined}"
    if store.root == "client":
        return f"${store.env[0]}/{joined}"
    return joined


def top_level_names(home: Path, run_root: Path) -> set[tuple[str, str]]:
    roots = {"home": home, "state": home / "state", "run": run_root, "lanes": home / "lanes"}
    return {(root, name) for root, path in roots.items() for name in _names(path)}


def _unregistered(roots: dict) -> list[dict]:
    rows = []
    for root in ("home", "state", "run", "lanes"):
        for name in _names(roots[root]):
            if inv.classify(root, name) is None:
                seen = file_inventory([roots[root] / name])
                rows.append({"root": root, "name": name, "files": seen["files"],
                             "bytes": seen["bytes"]})
    return rows


def _operation(value) -> dict:
    if isinstance(value, inv.Gap):
        return {"state": "gap", "reason": value.reason, "package": value.package}
    return {"state": "available"}


def store_row(store: inv.Store, roots: dict) -> dict:
    return {"id": store.id, "name": store.name, "root": store.root,
            "location": location_text(store),
            "classes": list(store.classes) if store.classes is not None else None,
            "owner_binding": store.owner_binding,
            "protection": {"kind": store.protection.kind, "reason": store.protection.reason,
                           "package": store.protection.package},
            "retention": store.retention,
            "caps": [{"what": c.what, "behavior": c.behavior, "test": c.test} for c in store.caps],
            "operations": {op: _operation(getattr(store, op)) for op in inv.OPERATIONS},
            "added_by_program": store.added_by_program, "invalidate": store.invalidate,
            "note": store.note, "evidence": store.evidence,
            "observed": file_inventory(store_paths(store, roots))}


def validate_row(row) -> list[str]:
    keys = {"id", "name", "root", "location", "classes", "owner_binding", "protection",
            "retention", "caps", "operations", "added_by_program", "invalidate", "note",
            "evidence", "observed"}
    if type(row) is not dict or set(row) != keys:
        return ["store row keys are wrong"]
    errors = []
    if row["classes"] is not None and not set(row["classes"]) <= set(inv.CLASS_NAMES):
        errors.append(f"{row['id']}: unknown data class")
    if row["root"] not in inv.ROOTS or row["protection"].get("kind") not in inv.PROTECTIONS:
        errors.append(f"{row['id']}: root or protection is unknown")
    if set(row["operations"]) != set(inv.OPERATIONS):
        errors.append(f"{row['id']}: operations are incomplete")
    if type(row["observed"].get("files")) is not int:
        errors.append(f"{row['id']}: observed counts are missing")
    return errors


def scan(environ=None) -> dict:
    """The `flywheel.trace-inventory/v1` document for the resolved home."""
    from .trace_custody_ledger import ledger_summary
    from .trace_enc_probe import encryption_status
    roots = resolve_roots(environ)
    rows = [store_row(store, roots) for store in inv.stores()]
    return {"schema": inv.SCHEMA, "generated_at": _iso(datetime.now(timezone.utc).timestamp()),
            "retention_default": inv.DEFAULT_RETENTION, "stores": rows,
            "unregistered": _unregistered(roots),
            "unclassified": [r["id"] for r in rows if r["classes"] is None],
            "ledger": ledger_summary(roots["home"]),
            "encryption": encryption_status(roots["state"]),
            "presence": _presence(roots["home"])}


def _presence(home) -> dict:
    from .trace_custody_ledger import read_owner_ref
    from .trace_presence import STATEMENT, presence_status
    owner = read_owner_ref(home)
    return presence_status(Path(home) / "state", owner) if owner else {
        "method": "none", "statement": STATEMENT}
