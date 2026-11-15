from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 200


def load_json_object(
    path: Path,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> dict[str, Any]:
    data = load_json(path, max_bytes=max_bytes, max_depth=max_depth)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def load_json(
    path: Path,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> Any:
    text = _read_bounded_text(path, max_bytes=max_bytes)
    _reject_excessive_nesting(text, max_depth=max_depth)
    return json.loads(
        text,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_nonfinite,
        parse_float=_finite_float,
    )


def _read_bounded_text(path: Path, *, max_bytes: int) -> str:
    with path.open("rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"JSON file exceeds {max_bytes} byte limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(str(exc)) from exc


def _reject_excessive_nesting(text: str, *, max_depth: int) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                raise ValueError(f"JSON nesting exceeds {max_depth} levels")
        elif char in "]}":
            depth = max(0, depth - 1)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"duplicate JSON key: {key}")
        data[key] = value
    return data


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON value: {value}")
    return parsed
