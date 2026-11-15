from __future__ import annotations

import unicodedata

_RESERVED = frozenset({
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})


def add_unique(violations: list[str], code: str) -> None:
    if code not in violations:
        violations.append(code)


def non_bool_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def normalize(value: str) -> str:
    if type(value) is not str:
        raise TypeError("value must be an exact str")
    return unicodedata.normalize("NFC", value).casefold()


def safe_identifier(value: object) -> bool:
    if type(value) is not str or value == "":
        return False
    if _has_control(value) or unicodedata.normalize("NFC", value) != value:
        return False
    if any(mark in value for mark in ("/", "\\", ":")) or value in (".", ".."):
        return False
    if value.endswith((" ", ".")):
        return False
    return value.split(".", 1)[0].casefold() not in _RESERVED


def safe_locator(value: object) -> bool:
    if type(value) is not str or value == "":
        return False
    if _has_control(value) or unicodedata.normalize("NFC", value) != value:
        return False
    if "\\" in value or ":" in value or value.startswith(("/", "//")):
        return False
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    return all(safe_identifier(part) for part in parts)


def tuple_or_original(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def _has_control(value: str) -> bool:
    return any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in value)
