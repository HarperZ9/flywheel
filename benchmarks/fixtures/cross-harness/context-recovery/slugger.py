"""Fixture source file for comp-005 context recovery."""


def normalize_slug(value: str) -> str:
    """Return a stable lowercase slug with single hyphen separators."""
    parts = [chunk for chunk in value.strip().lower().split() if chunk]
    return "-".join(parts)
