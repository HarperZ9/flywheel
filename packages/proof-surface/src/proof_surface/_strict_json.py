"""Shared strict JSON decoding for proof-bearing raw inputs.

Python's default decoder accepts duplicate object keys and non-finite numeric
constants. Both are ambiguous at a signed or hash-boundary, so file and text
entry points use this module before any contract-specific validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"strict loader: duplicate key {key!r}")
        decoded[key] = value
    return decoded


def _reject_constant(constant: str) -> Any:
    raise ValueError(f"strict loader: non-finite constant {constant!r} not allowed")


def strict_json_loads(text: str) -> Any:
    """Decode one JSON text while rejecting ambiguous JSON extensions."""
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def strict_json_load(path: str | Path) -> Any:
    """Read and strictly decode one UTF-8 JSON document from *path*."""
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))
