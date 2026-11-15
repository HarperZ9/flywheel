from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_RESERVED = frozenset({
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})


class SourceStateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class SourceStateItem:
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _require_source_path(self.path)
        _require_sha256("sha256", self.sha256)
        _require_non_negative_int("size", self.size)


def canonical_source_state(items: tuple[SourceStateItem, ...]) -> bytes:
    checked = _require_items(items)
    payload = [_item_dict(item) for item in sorted(checked, key=lambda item: item.path)]
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    return text.encode("utf-8")


def source_state_sha256(items: tuple[SourceStateItem, ...]) -> str:
    return "sha256:" + hashlib.sha256(canonical_source_state(items)).hexdigest()


def assert_source_state(
    expected_sha256: str,
    current: tuple[SourceStateItem, ...],
) -> None:
    _require_sha256("expected_sha256", expected_sha256, code="invalid-source-state")
    actual = source_state_sha256(current)
    if actual != expected_sha256:
        raise SourceStateError("source_changed", f"expected {expected_sha256}, got {actual}")


def _require_items(items: object) -> tuple[SourceStateItem, ...]:
    if type(items) is not tuple:
        raise SourceStateError("invalid-source-state", "items must be an exact tuple")
    seen: set[str] = set()
    for item in items:
        if type(item) is not SourceStateItem:
            raise SourceStateError("invalid-source-state", "items must contain exact SourceStateItem")
        _require_source_path(item.path)
        _require_sha256("sha256", item.sha256)
        _require_non_negative_int("size", item.size)
        key = _normalized_source_key(item.path)
        if key in seen:
            raise SourceStateError("duplicate-source-path", item.path)
        seen.add(key)
    return items


def _item_dict(item: SourceStateItem) -> dict[str, object]:
    return {"path": item.path, "sha256": item.sha256, "size": item.size}


def _require_source_path(path: object) -> None:
    if not isinstance(path, str) or path == "":
        _invalid_item("path must be a non-empty string")
    if "\0" in path or any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        _invalid_item("path contains control characters")
    if unicodedata.normalize("NFC", path) != path:
        _invalid_item("path must be NFC normalized")
    if "\\" in path or ":" in path or path.startswith(("/", "//")) or _DRIVE_RE.match(path):
        _invalid_item("path must be canonical relative POSIX")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _invalid_item("path contains unsafe segments")
    for part in parts:
        _reject_windows_alias(part)


def _require_sha256(name: str, value: object, *, code: str = "invalid-source-state-item") -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SourceStateError(code, f"{name} must be sha256:<64 lowercase hex>")


def _require_non_negative_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SourceStateError("invalid-source-state-item", f"{name} must be a non-bool int")


def _reject_windows_alias(part: str) -> None:
    if part.endswith((" ", ".")):
        _invalid_item("path segment has unsafe trailing character")
    if part.split(".", 1)[0].casefold() in _RESERVED:
        _invalid_item("path segment is a Windows device alias")


def _normalized_source_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _invalid_item(message: str) -> None:
    raise SourceStateError("invalid-source-state-item", message)
