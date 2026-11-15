"""versions_migrate.py -- the explicit-migrator seam.

M4.3 ships the pin registry (`versions.py`); this module ships the migration
seam that sits on top of it. The design is explicit-migrator-or-refuse (D-95):
same-pin migration is identity fast-path, cross-pin migration with no
registered migrator refuses `IncompatiblePin`, and any exception a registered
migrator raises wraps as `MigratorRaised(cause=original)` so the caller never
sees a bare leak.

Zero migrators ship at M4 close. `_MIGRATORS` is a module-level dict populated
by `register_migrator` and reset in tests via `pin_registry_scope` (versions.py
extends its snapshot to cover this module's registry too). The registry uses
`contextvars.ContextVar` for per-context override, mirroring `versions.py`.

Two refusal roots for the M4.3 surface: `VersionError` for lookup and compat
questions (versions.py) and `MigrationError` for the seam here.
`MigratorConflict` fires on duplicate `(from, to)` registration;
`MigratorRaised` wraps a raised exception with a stable class the caller can
catch without a bare `except Exception`.
"""
from __future__ import annotations

import contextvars
from typing import Protocol

from canon.schema import Record
from canon.versions import IncompatiblePin, SchemaPin


class MigrationError(Exception):
    """Root of the migration-seam refusal hierarchy. Distinct from
    `VersionError` (lookup and compat) so a caller may filter by concern."""


class MigratorConflict(MigrationError):
    """`register_migrator` called on a `(from_pin, to_pin)` pair that already
    has a registered migrator. Idempotent re-registration is refused so a
    fixture that would silently overwrite a real migrator fails loud."""


class MigratorRaised(MigrationError):
    """A registered migrator raised an exception. The original exception is
    attached as `cause` (and via `__cause__` for the traceback chain), so the
    caller catches one stable class instead of a bare `except Exception`."""

    def __init__(self, message: str, *, cause: BaseException):
        super().__init__(message)
        self.cause = cause


class MigrationFn(Protocol):
    """A migrator takes one record and returns one record. Structural typing
    only; no base class, no registration decorator. Callers wire callables of
    any shape that satisfies the signature."""

    def __call__(self, record: Record) -> Record: ...


_MIGRATORS: dict[tuple[SchemaPin, SchemaPin], MigrationFn] = {}

_MIGRATORS_OVERRIDE: contextvars.ContextVar[
    dict[tuple[SchemaPin, SchemaPin], MigrationFn] | None
] = contextvars.ContextVar("_MIGRATORS_OVERRIDE", default=None)


def _active_migrators() -> dict[tuple[SchemaPin, SchemaPin], MigrationFn]:
    override = _MIGRATORS_OVERRIDE.get()
    return override if override is not None else _MIGRATORS


def register_migrator(
    from_pin: SchemaPin,
    to_pin: SchemaPin,
    fn: MigrationFn,
) -> None:
    """Install `fn` as the migrator from `from_pin` to `to_pin`. Refuses
    `MigratorConflict` if the pair is already registered; `unregister_migrator`
    is the explicit remove path. Same-pin registration is refused with
    `ValueError` (identity migration needs no migrator and would shadow the
    fast path in `migrate`)."""
    if not isinstance(from_pin, SchemaPin) or not isinstance(to_pin, SchemaPin):
        raise ValueError(
            "register_migrator requires SchemaPin arguments, got "
            f"{type(from_pin)!r} and {type(to_pin)!r}")
    if from_pin == to_pin:
        raise ValueError(
            "register_migrator refuses identity migration; "
            "migrate(rec, pin, pin) is a fast-path identity call")
    reg = _active_migrators()
    key = (from_pin, to_pin)
    if key in reg:
        raise MigratorConflict(
            f"a migrator from {from_pin.kind_tag} to {to_pin.kind_tag} is "
            f"already registered")
    reg[key] = fn


def unregister_migrator(from_pin: SchemaPin, to_pin: SchemaPin) -> None:
    """Remove the migrator for `(from_pin, to_pin)` if one is installed.
    Idempotent: a missing entry is a no-op, not a refusal."""
    if not isinstance(from_pin, SchemaPin) or not isinstance(to_pin, SchemaPin):
        raise ValueError(
            "unregister_migrator requires SchemaPin arguments, got "
            f"{type(from_pin)!r} and {type(to_pin)!r}")
    _active_migrators().pop((from_pin, to_pin), None)


def migrate(record: Record, from_pin: SchemaPin, to_pin: SchemaPin) -> Record:
    """Return a record migrated from `from_pin` to `to_pin`. Identity fast-path
    on `from_pin == to_pin`. Refuses `IncompatiblePin` on a cross-pin call with
    no registered migrator. Wraps any exception the migrator raises as
    `MigratorRaised(..., cause=original)`."""
    if not isinstance(from_pin, SchemaPin) or not isinstance(to_pin, SchemaPin):
        raise ValueError(
            "migrate requires SchemaPin arguments, got "
            f"{type(from_pin)!r} and {type(to_pin)!r}")
    if from_pin == to_pin:
        return record
    fn = _active_migrators().get((from_pin, to_pin))
    if fn is None:
        raise IncompatiblePin(
            f"no migrator registered from {from_pin.kind_tag} to "
            f"{to_pin.kind_tag}")
    try:
        return fn(record)
    except (MigratorRaised, MigrationError):
        raise
    except Exception as exc:
        raise MigratorRaised(
            f"migrator from {from_pin.kind_tag} to {to_pin.kind_tag} "
            f"raised {type(exc).__name__}: {exc}",
            cause=exc,
        ) from exc
