"""Primitives shared by every cross-harness oracle checker.

These were defined inside `cross_harness_oracles` when one module held both the
dispatcher and every checker. A second checker module cannot import them from
there without a cycle, because the dispatcher imports the checker registry. So
they live here: no module in this package imports a checker from this file, and
this file imports nothing from the package.

The bodies are unchanged from their original definitions. `_root` takes `Any`
rather than `OracleContext` because the dataclass lives with the dispatcher; it
reads one mapping attribute and never needed the concrete type.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
from typing import Any
class _DuplicateKey(ValueError): pass
class _Malformed(ValueError): pass
def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in rows:
        if key in out: raise _DuplicateKey(key)
        out[key] = value
    return out
def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _read(checked, role: str, path: Path) -> bytes:
    for seen, data in checked.values():
        if seen == path: checked[role] = (path, data); return data
    data = path.read_bytes(); checked[role] = (path, data)
    return data
def _checked(items) -> list[dict[str, str]]:
    return [{"role": role, "basename": path.name, "sha256": _sha(data)}
            for role, (path, data) in sorted(items.items())]
def _inside(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value: return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts: return None
    try:
        path = (root / relative).resolve()
        return path if path.is_relative_to(root.resolve()) and path.is_file() else None
    except (OSError, RuntimeError): return None
def _admit(root: Path, value: Any) -> Path:
    if not isinstance(value, Path) or ".." in value.parts: raise _Malformed("attempt_path_invalid")
    try: path = (value if value.is_absolute() else root / value).resolve()
    except (OSError, RuntimeError) as exc: raise _Malformed("attempt_path_invalid") from exc
    if not path.is_relative_to(root): raise _Malformed("attempt_path_invalid")
    return path
def _rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise _Malformed(f"{field}_type_invalid")
    return value
def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _Malformed(f"{field}_type_invalid")
    return value
def _root(context: Any, field: str) -> Path:
    value = context.scorecard_core.get(field)
    if not isinstance(value, str) or not value: raise _Malformed(f"{field}_type_invalid")
    path = Path(value)
    if not path.is_dir(): raise _Malformed(f"{field}_directory_invalid")
    return path.resolve()
def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _Malformed(f"{field}_type_invalid")
    return value
