"""scope.py -- read what a record covers, under either field name.

Records name a `scope` list that says, in plain words, what the result covers.
Records written before the scope migration (2026-10-23) named the same list
`does_not_prove` and phrased each entry as a limit. Sealed and anchored
artifacts keep their bytes, so every reader goes through `scope_of` and accepts
both names. A record carries one of the two, never both: the older name marks
the older schema version, and each version is read with its own vocabulary.

The older name appears in code only through `LEGACY_SCOPE_KEY`;
scripts/check_scope_migration.py holds that line.
"""
from __future__ import annotations

from collections.abc import Mapping

SCOPE_KEY = "scope"
LEGACY_SCOPE_KEY = "does_not_prove"
SCOPE_KEYS = (SCOPE_KEY, LEGACY_SCOPE_KEY)


def scope_key(record: object) -> str | None:
    """The field name this record uses for its scope, or None when it has none.

    The older name wins when present, because a pre-migration record may also
    carry an unrelated string `scope` label beside its list.
    """
    if not isinstance(record, Mapping):
        return None
    if LEGACY_SCOPE_KEY in record:
        return LEGACY_SCOPE_KEY
    if SCOPE_KEY in record:
        return SCOPE_KEY
    return None


def scope_of(record: object, default=None):
    """The record's scope value as stored (list or string), under either name."""
    key = scope_key(record)
    return default if key is None else record[key]


def scope_list(record: object) -> list[str]:
    """The record's scope as a list of strings; a stored string is one entry."""
    value = scope_of(record)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        return [str(item) for item in value.values()]
    return [str(item) for item in value]


def has_both(record: object) -> bool:
    """True when a record carries the list under both names: a contract break."""
    return (isinstance(record, Mapping) and LEGACY_SCOPE_KEY in record
            and isinstance(record.get(SCOPE_KEY), (list, tuple)))
