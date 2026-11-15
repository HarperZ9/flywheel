"""backends/base.py -- the storage seam: the MemoryBackend Protocol.

F1 fixes the one interface every store adapter satisfies, so the renderer, the
migration legs, and the round-trip proof (R0) speak to a store through a single
shape and never to a concrete engine. A backend holds canonical Records and
hands them back field-identical -- except for the fields it has openly declared
it cannot hold. That honesty is the whole contract: `declared_drops()` names,
in capability tokens, what a round-trip through this backend loses, and `put()`
refuses a record that would lose a field silently.

Two kinds of drop live here. A *record-enforceable* drop is one a single record
can trigger by its own fields; F0's envelope has exactly one such capability,
`temporal` (a record carrying a live `valid_until` or `supersedes`). `guard_put`
refuses such a record on a backend that dropped the capability, so the loss is
never silent: the caller must `flatten()` first and thereby opt into it. A
*structural* drop (`arbitrary-kind`, `relations`, `audit-chain`,
`foreign-provenance`) is a property of the store, not of one record's fields; it
is declared and documented but cannot be triggered by a lone record, so
`guard_put` does not raise on it. Kind support is enforced separately, by
`supported_kinds()`.

canon stays self-contained: this module imports only the schema. The two
adapters that map external engines (mneme, flywheel) take an injected store
handle rather than importing the engine, so the container carries no runtime
dependency on either.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from canon.schema import Record

# Capability tokens. A backend's declared_drops() is a subset of these.
CAP_TEMPORAL = "temporal"
CAP_AUDIT_CHAIN = "audit-chain"
CAP_RELATIONS = "relations"
CAP_ARBITRARY_KIND = "arbitrary-kind"
CAP_FOREIGN_PROVENANCE = "foreign-provenance"

CAPABILITIES = frozenset({
    CAP_TEMPORAL,
    CAP_AUDIT_CHAIN,
    CAP_RELATIONS,
    CAP_ARBITRARY_KIND,
    CAP_FOREIGN_PROVENANCE,
})

# The one capability a single record can exercise by its own fields. The rest
# are structural properties of a store: declared, but not record-triggerable.
RECORD_ENFORCEABLE = frozenset({CAP_TEMPORAL})


class BackendError(Exception):
    """Base for every backend-level refusal."""


class UnsupportedKind(BackendError):
    """The backend does not hold this record's kind."""


class DropError(BackendError):
    """The record exercises a capability this backend cannot hold; the caller
    must flatten() to opt into the loss before storing. Raised by guard_put for
    a declared record-enforceable drop, and by a backend's own put() for a
    native limitation it enforces directly (mneme cannot store an externally
    supplied valid_until ordinal, so it refuses one rather than dropping it
    silently)."""


class MissingSupersedeTarget(BackendError):
    """A record supersedes a record that is not a present, current row in the
    store. mneme records a supersession only between two present rows and
    assigns the ordinal itself, so the superseded record must be stored first.
    Not resolvable by flatten(): it is an ordering precondition, not a dropped
    field."""


def record_key(record: Record) -> str:
    """The store-unique key for a record: its (scope, id) pair as a path. `id`
    alone is not unique -- a personality-block is deliberately present at both
    global and workspace under one id (the override case), so scope is part of
    the identity a backend stores under."""
    return f"{record.scope}/{record.id}"


def split_key(key: str) -> tuple[str, str]:
    """Inverse of record_key: (scope, id). id may itself contain '/'."""
    scope, _, rid = key.partition("/")
    return scope, rid


def temporal_in_use(record: Record) -> bool:
    """True iff the record carries actual temporal history: a live `valid_until`
    or a `supersedes` pointer. An all-null temporal block carries no history and
    is not 'in use'."""
    t = record.temporal
    return t is not None and (t.valid_until is not None or t.supersedes is not None)


def capabilities_required(record: Record) -> frozenset[str]:
    """The record-enforceable capabilities this single record exercises. Only
    `temporal`, and only when the temporal block holds history."""
    return frozenset({CAP_TEMPORAL}) if temporal_in_use(record) else frozenset()


def flatten_for_drops(record: Record, drops: frozenset[str]) -> Record:
    """A copy of `record` safe to store on a backend with these drops, with
    respect to the removable capabilities. Only `temporal` is removable at the
    record level; dropping it strips the temporal block to None."""
    if CAP_TEMPORAL in drops and temporal_in_use(record):
        return record.with_temporal(None)
    return record


def guard_put(backend: "MemoryBackend", record: Record) -> None:
    """The shared pre-store check every backend runs at the top of put(). Raises
    UnsupportedKind if the kind is not held, DropError if the record would
    silently lose a record-enforceable capability the backend dropped."""
    if record.kind not in backend.supported_kinds():
        raise UnsupportedKind(
            f"{backend.name} does not hold kind {record.kind!r}; "
            f"supported: {sorted(backend.supported_kinds())}")
    blocked = capabilities_required(record) & backend.declared_drops()
    if blocked:
        raise DropError(
            f"{backend.name} dropped {sorted(blocked)}; record {record.id!r} "
            f"exercises it -- flatten() to store current-only.")


@runtime_checkable
class MemoryBackend(Protocol):
    """The storage seam. A backend holds canonical Records under record_key()
    and returns them field-identical but for its declared drops."""

    name: str

    def supported_kinds(self) -> frozenset[str]:
        """The record kinds this backend holds. put() refuses others."""
        ...

    def declared_drops(self) -> frozenset[str]:
        """The capability tokens a round-trip through this backend loses."""
        ...

    def flatten(self, record: Record) -> Record:
        """A copy of `record` safe to put here, with dropped record-level
        capabilities removed. Identity when nothing is removable."""
        ...

    def put(self, record: Record) -> None:
        """Store a record. Raises UnsupportedKind / DropError per guard_put."""
        ...

    def get(self, key: str) -> Record | None:
        """The record stored under `key` (from record_key()), or None."""
        ...

    def records(self) -> list[Record]:
        """Every record held, order unspecified."""
        ...
