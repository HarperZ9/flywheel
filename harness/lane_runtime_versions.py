"""Validation for version strings exposed on lane status surfaces."""
from __future__ import annotations

import re

MAX_VERSION_LENGTH = 128

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")

_PEP440_RE = re.compile(
    r"^(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"
    r"(?:(?:a|b|c|rc|alpha|beta|pre|preview)[0-9]+)?"
    r"(?:(?:\.post|[-_]?post)[0-9]+)?"
    r"(?:(?:\.dev|[-_]?dev)[0-9]+)?"
    r"(?:\+[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)?$",
    re.IGNORECASE)


def normalize_public_version(value: object) -> str | None:
    """Return a public-safe package version, or None for malformed metadata."""
    if not isinstance(value, str):
        return None
    if not value or value != value.strip() or len(value) > MAX_VERSION_LENGTH:
        return None
    if _SEMVER_RE.fullmatch(value) or _PEP440_RE.fullmatch(value):
        return value
    return None


def validate_public_version(value: object, code: str) -> tuple[str | None, tuple[str, ...]]:
    version = normalize_public_version(value)
    return (version, ()) if version is not None else (None, (code,))
