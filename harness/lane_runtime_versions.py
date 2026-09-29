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


_RELEASE_RE = re.compile(r"^(?:([0-9]+)!)?([0-9]+(?:\.[0-9]+)*)(.*)$")
_PRE_RE = re.compile(r"^[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview|dev)", re.IGNORECASE)


def _release_key(value: str) -> tuple[int, tuple[int, ...], bool] | None:
    """(epoch, release numbers without trailing zeros, is a pre-release)."""
    match = _RELEASE_RE.match(value.strip())
    if match is None:
        return None
    numbers = [int(part) for part in match.group(2).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return int(match.group(1) or 0), tuple(numbers), bool(_PRE_RE.match(match.group(3)))


def version_below(installed: str, pin: str) -> bool:
    """True when ``installed`` is an older release than ``pin``. A pre-release
    or dev build of the pinned number counts as older; a post or local build
    does not. An unparseable value is never judged older here: the caller's
    validation names it."""
    have, want = _release_key(installed), _release_key(pin)
    if have is None or want is None:
        return False
    if have[:2] != want[:2]:
        return have[:2] < want[:2]
    return have[2] and not want[2]
