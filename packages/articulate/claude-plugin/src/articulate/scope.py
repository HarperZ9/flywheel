"""The scope field: what a result covers, said plainly.

Version 2 reports and receipts carry a `scope` field. Version 1 named the same
field `does_not_prove`. `scope_of` reads both names, so a version 1 file still
loads and verifies. `without_scope` removes both names, so a verifier can
compare a version 1 record with a record made now.
"""
KEY = "scope"
LEGACY_KEY = "does_not_prove"


def scope_of(record, default=""):
    """The scope text of a record of either version."""
    if not isinstance(record, dict):
        return default
    return record.get(KEY, record.get(LEGACY_KEY, default))


def without_scope(value):
    """A copy of value with every scope field removed, at any depth."""
    if isinstance(value, dict):
        return {k: without_scope(v) for k, v in value.items() if k not in (KEY, LEGACY_KEY)}
    if isinstance(value, list):
        return [without_scope(v) for v in value]
    return value
